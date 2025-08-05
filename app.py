import zipfile
import xml.etree.ElementTree as ET
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import tempfile
import os
from io import BytesIO

app = Flask(__name__)
CORS(app)

def studio3_to_svg(studio3_path):
    # Verifica se o arquivo é ZIP (versões antigas do .studio3)
    if not zipfile.is_zipfile(studio3_path):
        app.logger.warning("Arquivo não é um ZIP — possivelmente Silhouette Studio versão 5 ou exportado.")
        raise ValueError(
            "Este arquivo .studio3 não é suportado diretamente. "
            "Provavelmente foi criado no Silhouette Studio versão 5 ou superior. "
            "Exporte para SVG ou DXF no Silhouette Studio e envie novamente."
        )

    try:
        with zipfile.ZipFile(studio3_path, 'r') as z:
            xml_file = None
            for name in z.namelist():
                if name.endswith("document.xml"):
                    xml_file = name
                    break
            if not xml_file:
                raise ValueError("Arquivo .studio3 inválido ou corrompido (sem document.xml).")

            with z.open(xml_file) as f:
                tree = ET.parse(f)
                root = tree.getroot()

    except zipfile.BadZipFile:
        raise ValueError("Arquivo .studio3 inválido ou corrompido.")
    except Exception as e:
        app.logger.error(f"Erro inesperado ao abrir .studio3: {e}")
        raise

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
    return svg_content

@app.route('/convert', methods=['POST'])
def convert_file():
    if 'file' not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    file = request.files['file']
    filename = file.filename.lower()

    # Salva o arquivo temporariamente
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        file.save(tmp.name)
        temp_path = tmp.name

    try:
        # Se for .studio3 → tentar converter
        if filename.endswith(".studio3"):
            try:
                svg_data = studio3_to_svg(temp_path)
                os.unlink(temp_path)
                output_name = os.path.splitext(file.filename)[0] + ".svg"

                return send_file(
                    BytesIO(svg_data.encode('utf-8')),
                    mimetype='image/svg+xml',
                    as_attachment=True,
                    download_name=output_name
                )
            except ValueError as ve:
                os.unlink(temp_path)
                return jsonify({"error": str(ve)}), 400

        # Se for SVG ou DXF → retorna o próprio arquivo (pass-through)
        elif filename.endswith(".svg") or filename.endswith(".dxf"):
            with open(temp_path, "rb") as f:
                data = f.read()
            os.unlink(temp_path)
            return send_file(
                BytesIO(data),
                mimetype='image/svg+xml' if filename.endswith(".svg") else 'application/dxf',
                as_attachment=True,
                download_name=file.filename
            )

        else:
            os.unlink(temp_path)
            return jsonify({"error": "Formato inválido. Envie .studio3, .svg ou .dxf"}), 400

    except Exception as e:
        os.unlink(temp_path)
        app.logger.error(f"Erro interno no servidor: {e}")
        return jsonify({"error": "Erro interno no servidor"}), 500

@app.route('/', methods=['GET'])
def home():
    return "API de conversão .studio3 (antigos) e envio de SVG/DXF funcionando."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
