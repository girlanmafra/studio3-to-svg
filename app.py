import zipfile
import xml.etree.ElementTree as ET
import re
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import tempfile
import os
from io import BytesIO
from xml.sax.saxutils import escape

app = Flask(__name__)
CORS(app)

SVG_COMMANDS_PARAMS = {
    'M': 2, 'L': 2, 'H': 1, 'V': 1,
    'C': 6, 'S': 4, 'Q': 4, 'T': 2,
    'A': 7, 'Z': 0
}

def remove_namespace(tag):
    return tag.split('}')[-1] if '}' in tag else tag

def is_valid_path(d_attr):
    try:
        tokens = re.findall(r'[A-Za-z]|[-+]?\d*\.?\d+', d_attr)
        i = 0
        while i < len(tokens):
            cmd = tokens[i]
            if not re.match(r'[MmLlHhVvCcSsQqTtAaZz]', cmd):
                return False
            i += 1
            required = SVG_COMMANDS_PARAMS.get(cmd.upper(), None)
            if required is None:
                return False
            param_count = 0
            while i < len(tokens) and not re.match(r'[A-Za-z]', tokens[i]):
                param_count += 1
                i += 1
            if required == 0:
                continue
            if param_count < required or param_count % required != 0:
                return False
        return True
    except Exception:
        return False

def auto_close_path(d: str) -> str:
    coords = re.findall(r'[-+]?\d*\.?\d+', d)
    if len(coords) < 4:
        return d
    try:
        x0, y0 = float(coords[0]), float(coords[1])
        xN, yN = float(coords[-2]), float(coords[-1])
        if abs(x0 - xN) < 0.01 and abs(y0 - yN) < 0.01:
            if not d.strip().endswith(('Z', 'z')):
                return d.strip() + ' Z'
    except Exception:
        pass
    return d

def gerar_svg(svg_paths, width=210, height=297):
    px_width = width * 3.7795
    px_height = height * 3.7795
    svg_header = f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg xmlns="http://www.w3.org/2000/svg"
     version="1.1"
     width="{width}mm"
     height="{height}mm"
     viewBox="0 0 {px_width:.2f} {px_height:.2f}">
<g id="Layer_1" fill="none" stroke="black" stroke-width="1">
"""
    svg_footer = "\n</g>\n</svg>"
    return svg_header + "\n".join(svg_paths) + svg_footer

def process_xml_svg(file_like):
    tree = ET.parse(file_like)
    root = tree.getroot()

    svg_paths = []
    for elem in root.iter():
        tag = remove_namespace(elem.tag).lower()
        d = elem.attrib.get('d')
        if d and is_valid_path(d):
            d_closed = auto_close_path(d)
            svg_paths.append(f'<path d="{escape(d_closed)}" />')

    if not svg_paths:
        raise ValueError("Nenhum path válido encontrado no XML.")

    return gerar_svg(svg_paths)

def studio_file_to_svg(filepath):
    # Detecta arquivos binários (v5+)
    with open(filepath, 'rb') as f:
        header = f.read(4)
        if not header.startswith(b'PK') and not header.strip().startswith(b'<'):
            raise ValueError(
                "Este arquivo .studio/.gsp é binário (v5+) e não pode ser convertido. "
                "Salve como Studio v2 ou use GSP/XML."
            )

    try:
        # Tenta como ZIP
        with zipfile.ZipFile(filepath, 'r') as z:
            for name in z.namelist():
                if name.endswith(".xml") or "document" in name:
                    with z.open(name) as f:
                        return process_xml_svg(f)
        raise ValueError("Arquivo ZIP sem XML reconhecível.")
    except zipfile.BadZipFile:
        # Tenta como XML puro
        with open(filepath, 'rb') as f:
            return process_xml_svg(f)

@app.route('/convert', methods=['POST'])
def convert_file():
    if 'file' not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    file = request.files['file']
    filename = file.filename.lower()

    if not filename.endswith(('.studio3', '.studio', '.gsp')):
        return jsonify({"error": "Formato inválido. Envie um arquivo .studio3, .studio ou .gsp"}), 400

    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            file.save(tmp.name)
            svg_data = studio_file_to_svg(tmp.name)
            os.unlink(tmp.name)

        output_name = os.path.splitext(file.filename)[0] + ".svg"

        return send_file(
            BytesIO(svg_data.encode('utf-8')),
            mimetype='image/svg+xml',
            as_attachment=True,
            download_name=output_name
        )

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        app.logger.error(f"Erro interno no servidor: {e}")
        return jsonify({"error": "Erro interno no servidor"}), 500

@app.route('/validate', methods=['POST'])
def validate_svg():
    if 'file' not in request.files:
        return jsonify({"error": "Nenhum arquivo SVG enviado"}), 400

    file = request.files['file']
    if not file.filename.endswith(".svg"):
        return jsonify({"error": "O arquivo deve ter extensão .svg"}), 400

    try:
        svg_content = file.read().decode("utf-8")
        if "<svg" not in svg_content or "<path" not in svg_content:
            return jsonify({"error": "O arquivo não contém dados SVG visíveis"}), 400
        return svg_content, 200, {'Content-Type': 'image/svg+xml'}
    except Exception as e:
        app.logger.error(f"Erro na validação do SVG: {e}")
        return jsonify({"error": "Erro ao processar o arquivo SVG"}), 500

@app.route('/', methods=['GET'])
def home():
    return "API de conversão .studio/.gsp para .svg funcionando."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
