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


def detect_binary_format(filepath):
    try:
        with open(filepath, 'rb') as f:
            header = f.read(128)

        if header.startswith(b"GRAPHTEC PRT&CUT"):
            return "GSP (Graphtec binário)"
        if header.startswith(b"silhouette04;"):
            return "Studio v2 (binário)"
        if header.startswith(b"silhouette05;"):
            return "Studio3 (v5+ binário)"
        return None
    except Exception:
        return "desconhecido"


def process_xml_svg_bytes(content_bytes):
    svg_paths = []
    root = None

    for enc in ('utf-8-sig', 'utf-16', 'latin-1'):
        try:
            decoded = content_bytes.decode(enc)
            root = ET.fromstring(decoded)
            break
        except Exception:
            continue

    if root is None:
        raise ValueError("Falha ao processar o arquivo XML. Verifique se o arquivo é válido.")

    for elem in root.iter():
        tag = remove_namespace(elem.tag).lower()

        d = elem.attrib.get('d')
        if d and is_valid_path(d):
            d_closed = auto_close_path(d)
            svg_paths.append(f'<path d="{escape(d_closed)}" />')

        for child in elem:
            child_tag = remove_namespace(child.tag).lower()
            d2 = child.attrib.get('d')
            if d2 and is_valid_path(d2):
                d_closed = auto_close_path(d2)
                svg_paths.append(f'<path d="{escape(d_closed)}" />')

    if not svg_paths:
        raise ValueError("Nenhum path válido encontrado no XML.")

    return gerar_svg(svg_paths)


def studio_file_to_svg(filepath):
    tipo_binario = detect_binary_format(filepath)
    if tipo_binario:
        raise ValueError(
            f"⚠️ O arquivo parece estar em formato binário ({tipo_binario}).\n"
            "Por favor, salve como Studio V2 XML, GSP XML ou utilize exportação SVG se disponível."
        )

    try:
        with zipfile.ZipFile(filepath, 'r') as z:
            for name in z.namelist():
                if name.endswith(".xml") or "document" in name:
                    with z.open(name) as f:
                        return process_xml_svg_bytes(f.read())
        raise ValueError("Arquivo ZIP sem XML reconhecível.")
    except zipfile.BadZipFile:
        with open(filepath, 'rb') as f:
            return process_xml_svg_bytes(f.read())


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


@app.route('/', methods=['GET'])
def home():
    return "API de conversão .studio/.gsp para .svg funcionando."


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
