import zipfile
import xml.etree.ElementTree as ET
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import tempfile
import os
from io import BytesIO
import logging

app = Flask(__name__)
CORS(app)

# Configura logging para o console
logging.basicConfig(level=logging.DEBUG)

def studio3_to_svg(studio3_path):
    app.logger.debug(f"Começando conversão do arquivo: {studio3_path}")
    try:
        with zipfile.ZipFile(studio3_path, 'r') as z:
            xml_file = None
            for name in z.namelist():
                if name.endswith("document.xml"):
                    xml_file = name
                    break
            if not xml_file:
                raise ValueError("Arquivo .studio3 inválido ou corrompido (document.xml não encontrado).")
            with z.open(xml_file) as f:
                tree = ET.parse(f)
                root = tree.getroot()
        svg_paths = []
        for elem in root.iter():
            tag = elem.tag.lower()
            if 'path' in tag or 'polyline' in tag or 'line' in tag:
                d = elem.attrib.get('d')
                if d:
                    svg_paths.append(f'<path d="{d}" fill="none" stroke="black" stroke-width="1"/>')
        svg_content = f"""<?xml version="1.0" standalone="no"?>
<svg xmlns="http://www.w3.org/2000/svg" version="1.1">
{''.join(svg_paths)}
</svg>
"""
        app.logger.debug("Conversão finalizada com sucesso.")
        return svg_content
    except Exception as e:
        app.logger.error(f"Erro na conversão: {e}")
        raise

@app.route('/convert', methods=['POST'])
def convert_file():
    app.logger.debug("Recebendo requisição /convert")
    try:
        if 'file' not in request.files:
            app.logger.warning("Nenhum arquivo enviado na requisição.")
            return jsonify({"error": "Nenhum arquivo enviado"}), 400
        
        file = request.files['file']
        app.logger.debug(f"Arquivo recebido: {file.filename}")
        
        if not file.filename.endswith(".studio3"):
            app.logger.warning(f"Arquivo inválido enviado: {file.filename}")
            return jsonify({"error": "Formato inválido, envie um arquivo .studio3"}), 400

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            file.save(tmp.name)
            app.logger.debug(f"Arquivo salvo temporariamente em: {tmp.name}")
            svg_data = studio3_to_svg(tmp.name)
            os.unlink(tmp.name)  # remove o arquivo temporário

        output_name = os.path.splitext(file.filename)[0] + ".svg"
        app.logger.debug(f"Preparando resposta com o arquivo: {output_name}")

        return send_file(
            BytesIO(svg_data.encode('utf-8')),
            mimetype='image/svg+xml',
            as_attachment=True,
            download_name=output_name
        )
    except Exception as e:
        app.logger.error(f"Erro no endpoint /convert: {e}")
        return jsonify({"error": f"Erro interno: {str(e)}"}), 500

@app.route('/', methods=['GET'])
def home():
    return "API de conversão .studio3 para .svg funcionando."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
