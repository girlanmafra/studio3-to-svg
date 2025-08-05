import zipfile
import xml.etree.ElementTree as ET
import re
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import tempfile
import os
from io import BytesIO

app = Flask(__name__)
CORS(app)


def studio3_to_svg(studio3_path):
    try:
        # Tentar abrir como ZIP (versões antigas)
        with zipfile.ZipFile(studio3_path, 'r') as z:
            xml_file = next((name for name in z.namelist() if name.endswith("document.xml")), None)
            if not xml_file:
                raise ValueError("Arquivo .studio3 ZIP sem document.xml.")

            with z.open(xml_file) as f:
                tree = ET.parse(f)
                root = tree.getroot()

            svg_paths = []
            for elem in root.iter():
                tag = elem.tag.lower()
                d = elem.attrib.get('d')
                if d and any(cmd in d for cmd in "MLCQAZmlcqaz"):  # comandos válidos SVG
                    svg_paths.append(f'<path d="{d}" fill="none" stroke="black" stroke-width="1"/>')

            if not svg_paths:
                raise ValueError("Nenhuma forma encontrada no document.xml.")

            return gerar_svg(svg_paths)

    except zipfile.BadZipFile:
        # Arquivo binário (v5+)
        return processar_binario(studio3_path)


def processar_binario(filepath):
    with open(filepath, "rb") as f:
        data = f.read()

    # Regex aprimorado: começa com comando SVG, segue por números, espaços, vírgulas e negativos
    pattern = rb'([MmLlHhVvCcSsQqTtAaZz][0-9\.\,\-\s]{2,200})'
    matches = re.findall(pattern, data)

    svg_paths = []
    for m in matches:
        try:
            d = m.decode("utf-8", errors="ignore").strip()
            if re.match(r'^[MLCQAZmlcqaz][0-9\.\,\-\s]+$', d):  # valida estrutura
                svg_paths.append(f'<path d="{d}" fill="none" stroke="black" stroke-width="1"/>')
        except:
            continue

    if not svg_paths:
        raise ValueError("Nenhum path SVG válido extraído do binário .studio3")

    return gerar_svg(svg_paths)


def gerar_svg(paths):
    # Gerar SVG com header e viewBox compatível com CanvasWorkspace
    svg = f'''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg
    xmlns="http://www.w3.org/2000/svg"
    version="1.1"
    width="300mm"
    height="300mm"
    viewBox="0 0 300 300">
    {"".join(paths)}
</svg>
'''
    return svg


@app.route('/convert', methods=['POST'])
def convert_file():
    if 'file' not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    file = request.files['file']
    if not file.filename.endswith(".studio3"):
        return jsonify({"error": "Envie um arquivo .studio3"}), 400

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
        app.logger.error(f"Erro no servidor: {e}")
        return jsonify({"error": "Erro interno no servidor"}), 500


@app.route('/', methods=['GET'])
def home():
    return "API .studio3 → SVG online (compatível com CanvasWorkspace)"


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
