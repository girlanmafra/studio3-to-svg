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

# SVG path commands and expected parameter counts
SVG_COMMANDS_PARAMS = {
    'M': 2, 'L': 2, 'H': 1, 'V': 1,
    'C': 6, 'S': 4, 'Q': 4, 'T': 2,
    'A': 7, 'Z': 0
}


def remove_namespace(tag):
    return tag.split('}')[-1] if '}' in tag else tag


def is_valid_path(d_attr):
    tokens = re.findall(r'([MmLlHhVvCcSsQqTtAaZz])|(-?\d+(?:\.\d+)?)', d_attr)
    if not tokens:
        return False

    cmd = None
    args = []
    expected = 0

    for t in tokens:
        if t[0]:  # command letter
            if cmd and expected and len(args) % expected != 0:
                return False
            cmd = t[0].upper()
            expected = SVG_COMMANDS_PARAMS.get(cmd, None)
            if expected is None:
                return False
            args = []
        elif t[1]:  # number
            args.append(float(t[1]))

    if expected and len(args) % expected != 0:
        return False
    return True


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
    """Creates an SVG with mm dimensions and a viewBox in px"""
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


def processar_binario(filepath):
    """Processes binary .studio3 files (Silhouette v5+)"""
    with open(filepath, "rb") as f:
        raw = f.read()

    ascii_data = ''.join(chr(b) if 32 <= b <= 126 else ' ' for b in raw)
    pattern = re.compile(r'([MmLlHhVvCcSsQqTtAaZz][0-9.,\s\-]{10,})')
    matches = pattern.findall(ascii_data)

    svg_paths = []
    for d in matches:
        d = d.strip()
        if is_valid_path(d):
            d_closed = auto_close_path(d)
            svg_paths.append(f'<path d="{escape(d_closed)}" />')

    if not svg_paths:
        raise ValueError("Não foi possível extrair paths SVG válidos do arquivo binário.")

    return gerar_svg(svg_paths)


def studio3_to_svg(studio3_path):
    """Processes .studio3 files (ZIP/XML or binary)"""
    try:
        with zipfile.ZipFile(studio3_path, 'r') as z:
            xml_file = next((name for name in z.namelist() if name.endswith("document.xml")), None)
            if not xml_file:
                raise ValueError("Arquivo ZIP sem document.xml")

            with z.open(xml_file) as f:
                tree = ET.parse(f)
                root = tree.getroot()

            svg_paths = []
            for elem in root.iter():
                tag = remove_namespace(elem.tag).lower()
                d = elem.attrib.get('d')
                if d and is_valid_path(d):
                    d_closed = auto_close_path(d)
                    svg_paths.append(f'<path d="{escape(d_closed)}" />')

            if not svg_paths:
                raise ValueError("document.xml encontrado, mas sem paths válidos.")

            return gerar_svg(svg_paths)

    except zipfile.BadZipFile:
        return processar_binario(studio3_path)


@app.route('/convert', methods=['POST'])
def convert_file():
    if 'file' not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    file = request.files['file']
    if not file.filename.endswith(".studio3"):
        return jsonify({"error": "Formato inválido, envie um arquivo .studio3"}), 400

    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            file.save(tmp.name)
            svg_data = studio3_to_svg(tmp.name)
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
    return "API de conversão .studio3 para .svg funcionando."


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
