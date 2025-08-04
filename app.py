import zipfile
import xml.etree.ElementTree as ET
from flask import Flask, request, send_file, jsonify
import tempfile
import os
from io import BytesIO

app = Flask(__name__)

def studio3_to_svg(studio3_path):
    # Abre o arquivo .studio3 como ZIP
    with zipfile.ZipFile(studio3_path, 'r') as z:
        # Encontra o XML principal
        xml_file = None
        for name in z.namelist():
            if name.endswith("document.xml"):
                xml_file = name
                break
        if not xml_file:
            raise ValueError("Arquivo .studio3 inválido ou corrompido.")

        # Lê o XML
        with z.open(xml_file) as f:
            tree = ET.parse(f)
            root = tree.getroot()

    # Extrai apenas os elementos de linha e caminho
    svg_paths = []
    for elem in root.iter():
        tag = elem.tag.lower()
        if 'path' in tag or 'polyline' in tag or 'line' in tag:
            d = elem.attrib.get('d')  # Caminho no formato SVG
            if d:
                svg_paths.append(f'<path d="{d}" fill="none" stroke="black" stroke-width="1"/>')

    # Monta o SVG
    svg_content = f"""<?xml version="1.0" standalone="no"?>
<svg xmlns="http://www.w3.org/2000/svg" version="1.1">
{''.join(svg_paths)}
</svg>
"""
    return svg_content

@app.route('/convert', methods=['POST'])
def convert_file():
    if 'file' not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400
    
    file = request.files['file']
    if not file.filename.endswith(".studio3"):
        return jsonify({"error": "Formato inválido, envie um arquivo .studio3"}), 400

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        file.save(tmp.name)
        svg_data = studio3_to_svg(tmp.name)

    # Nome do arquivo de saída
    output_name = os.path.splitext(file.filename)[0] + ".svg"

    # Retorna como arquivo para download
    return send_file(
        BytesIO(svg_data.encode('utf-8')),
        mimetype='image/svg+xml',
        as_attachment=True,
        download_name=output_name
    )

@app.route('/', methods=['GET'])
def home():
    return "API de conversão .studio3 para .svg funcionando."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
