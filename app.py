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

def remove_namespace(tag):
    return tag.split('}')[-1] if '}' in tag else tag

def gerar_svg(svg_paths):
    """Gera um SVG minimalista e compatível com CanvasWorkspace"""
    return (
        '<?xml version="1.0" standalone="no"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" version="1.1">\n'
        + ''.join(svg_paths) +
        '\n</svg>'
    )

def validar_path_svg(d):
    """Verifica se o atributo 'd' contém ao menos um comando SVG válido"""
    if not re.fullmatch(r'[MmLlHhVvCcSsQqTtAaZz0-9.,\s\-]+', d):
        return False
    return len(re.findall(r'[MmLlHhVvCcSsQqTtAaZz]', d)) >= 1 and len(d) > 5

def studio3_to_svg(studio3_path):
    try:
        with zipfile.ZipFile(studio3_path, 'r') as z:
            xml_file = next((n for n in z.namelist() if n.endswith("document.xml")), None)
            if not xml_file:
                raise ValueError("Arquivo ZIP não contém document.xml.")

            with z.open(xml_file) as f:
                tree = ET.parse(f)
                root = tree.getroot()

            svg_paths = []
            for elem in root.iter():
                tag = remove_namespace(elem.tag).lower()
                if 'path' in tag or 'polyline' in tag or 'line' in tag:
                    d = elem.attrib.get('d')
                    if d and validar_path_svg(d):
                        svg_paths.append(f'<path d="{escape(d)}" fill="none" stroke="black" stroke-width="1"/>')

            if not svg_paths:
                raise ValueError("Nenhum path válido encontrado no XML.")

            return gerar_svg(svg_paths)

    except zipfile.BadZipFile:
        return processar_binario(studio3_path)

def processar_binario(filepath):
    with open(filepath, "rb") as f:
        data = f.read()

    matches = re.findall(rb'[MmLlHhVvCcSsQqTtAaZz][^MmLlHhVvCcSsQqTtAaZz]{1,200}', data)

    svg_paths = []
    for m in matches:
        try:
            d = m.decode("utf-8", errors="ignore").strip()
            if validar_path_svg(d):
                svg_paths.append(f'<path d="{escape(d)}" fill="none" stroke="black" stroke-width="1"/>')
        except:
            continue

    if not svg_paths:
        raise ValueError("Nenhum path válido extraído do binário.")

    return gerar_svg(svg_paths)

@app.route('/convert', methods=['POST'])
def convert_file():
    if 'file' not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    file = request.files['file']
    if not file.filename.endswith(".studio3"):
        return jsonify({"error": "Formato inválido. Envie um arquivo .studio3"}), 400

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
        app.logger.error(f"Erro interno: {e}")
        return jsonify({"error": "Erro interno no servidor"}), 500

@app.route('/', methods=['GET'])
def home():
    return "API de conversão .studio3 para .svg funcionando."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
