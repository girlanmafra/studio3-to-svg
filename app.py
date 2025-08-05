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
CORS(app, resources={r"/*": {"origins": "*"}})


def remove_namespace(tag):
    return tag.split('}')[-1] if '}' in tag else tag


def gerar_svg(svg_paths, width=210, height=297):
    """Monta SVG com viewBox e dimensões físicas (A4 size default)"""
    svg_header = f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg 
    xmlns="http://www.w3.org/2000/svg" 
    version="1.1" 
    width="{width}mm" 
    height="{height}mm" 
    viewBox="0 0 {width * 3.7795:.2f} {height * 3.7795:.2f}">
<g id="Layer_1" fill="none" stroke="black" stroke-width="1">
"""
    svg_footer = "</g>\n</svg>"
    return svg_header + "\n".join(svg_paths) + svg_footer


def processar_binario(filepath):
    with open(filepath, "rb") as f:
        raw = f.read()

    ascii_data = ''.join(chr(b) if 32 <= b <= 126 else ' ' for b in raw)
    pattern = re.compile(r'([MmLlHhVvCcSsQqTtAaZz][0-9.,\s\-]{10,})')
    matches = pattern.findall(ascii_data)

    svg_paths = []
    for d in matches:
        d = d.strip()
        if not re.fullmatch(r'[MmLlHhVvCcSsQqTtAaZz0-9.,\s\-]+', d):
            continue
        num_count = len(re.findall(r'-?\d+(?:\.\d+)?', d))
        if num_count < 2:
            continue
        svg_paths.append(f'<path d="{escape(d)}" />')

    if not svg_paths:
        raise ValueError("Nenhum caminho válido foi encontrado no arquivo binário.")

    return gerar_svg(svg_paths)


def studio3_to_svg(studio3_path):
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
                if d and re.fullmatch(r'[MmLlHhVvCcSsQqTtAaZz0-9.,\s\-]+', d):
                    svg_paths.append(f'<path d="{escape(d)}" />')

            if not svg_paths:
                raise ValueError("document.xml encontrado, mas sem paths.")

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
            return jsonify({"error": "O arquivo não parece conter conteúdo SVG válido"}), 400

        return svg_content, 200, {'Content-Type': 'image/svg+xml'}

    except Exception as e:
        app.logger.error(f"Erro na validação do SVG: {e}")
        return jsonify({"error": "Erro ao processar o arquivo SVG"}), 500


@app.route('/', methods=['GET'])
def home():
    return "API de conversão .studio3 para .svg funcionando."


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
