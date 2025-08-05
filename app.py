import zipfile
import xml.etree.ElementTree as ET
import re
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import tempfile
import os
from io import BytesIO

app = Flask(__name__)
CORS(app)  # Permite requisições de qualquer origem

def studio3_to_svg(studio3_path):
    # Primeiro: tentar abrir como ZIP (arquivos antigos do Silhouette)
    try:
        with zipfile.ZipFile(studio3_path, 'r') as z:
            xml_file = None
            for name in z.namelist():
                if name.endswith("document.xml"):
                    xml_file = name
                    break
            if not xml_file:
                raise ValueError("Arquivo .studio3 ZIP sem document.xml interno.")

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

            return gerar_svg(svg_paths)

    except zipfile.BadZipFile:
        # Não é ZIP → tratar como binário da versão 5
        return processar_binario(studio3_path)


def processar_binario(filepath):
    """Lê arquivos .studio3 binários (Silhouette v5+) e extrai comandos de path"""
    with open(filepath, "rb") as f:
        data = f.read()

    # Regex para capturar comandos SVG no binário
    matches = re.findall(rb'[MmLlHhVvCcSsQqTtAaZz][^MmLlHhVvCcSsQqTtAaZz]{1,200}', data)

    svg_paths = []
    for m in matches:
        try:
            d = m.decode("utf-8", errors="ignore").strip()
            if len(d) > 2:
                svg_paths.append(f'<path d="{d}" fill="none" stroke="black" stroke-width="1"/>')
        except:
            pass

    if not svg_paths:
        raise ValueError("Não foi possível extrair formas do arquivo .studio3")

    return gerar_svg(svg_paths)


def gerar_svg(svg_paths):
    """Monta o SVG final"""
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
        app.logger.warning(f"Arquivo inválido enviado: {file.filename}")
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


@app.route('/', methods=['GET'])
def home():
    return "API de conversão .studio3 para .svg funcionando."


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
