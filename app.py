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
    """Monta o SVG final com cabeçalho e paths com dimensões em milímetros"""
    svg_content = f"""<?xml version="1.0" standalone="no"?>
<svg xmlns="http://www.w3.org/2000/svg"
     version="1.1"
     width="100mm" height="100mm"
     viewBox="0 0 100 100"
     xmlns:xlink="http://www.w3.org/1999/xlink">
{''.join(svg_paths)}
</svg>
"""
    return svg_content

def processar_binario(filepath):
    """Extrai paths válidos de arquivos .studio3 binários (Silhouette v5+)"""
    with open(filepath, "rb") as f:
        data = f.read()

    pattern = rb'([MmLlHhVvCcSsQqTtAaZz][0-9.,\s\-]{5,300})'
    matches = re.findall(pattern, data)

    svg_paths = []
    for m in matches:
        try:
            d = m.decode("utf-8", errors="ignore").strip()
            if not re.search(r'\d', d):
                continue
            if len(re.findall(r'\d+', d)) < 2:
                continue
            if re.fullmatch(r'[MmLlHhVvCcSsQqTtAaZz0-9.,\s\-]+', d):
                svg_paths.append(f'<path d="{escape(d)}" fill="none" stroke="black" stroke-width="0.2"/>')
        except Exception:
            continue

    if not svg_paths:
        raise ValueError("Não foi possível extrair caminhos válidos do arquivo .studio3 binário")

    return gerar_svg(svg_paths)

def studio3_to_svg(studio3_path):
    """Processa arquivos .studio3 (ZIP antigos ou binário v5+)"""
    try:
        with zipfile.ZipFile(studio3_path, 'r') as z:
            xml_file = next((name for name in z.namelist() if name.endswith("document.xml")), None)
            if not xml_file:
                raise ValueError("Arquivo .studio3 ZIP sem document.xml interno.")

            with z.open(xml_file) as f:
                tree = ET.parse(f)
                root = tree.getroot()

            svg_paths = []
            for elem in root.iter():
                tag = remove_namespace(elem.tag).lower()
                if 'path' in tag or 'polyline' in tag or 'line' in tag:
                    d = elem.attrib.get('d')
                    if d and re.fullmatch(r'[MmLlHhVvCcSsQqTtAaZz0-9.,\s\-]+', d):
                        svg_paths.append(f'<path d="{escape(d)}" fill="none" stroke="black" stroke-width="0.2"/>')

            if not svg_paths:
                raise ValueError("Nenhum path encontrado no document.xml")

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
