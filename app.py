import zipfile
import xml.etree.ElementTree as ET
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import tempfile
import os
from io import BytesIO

app = Flask(__name__)
CORS(app)

def parse_silhouette_xml(xml_data):
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError:
        raise ValueError("Erro ao interpretar o XML do arquivo Silhouette.")

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

def silhouette_to_svg(file_path):
    # Primeiro: tenta abrir como ZIP (ex: .studio3 antigo)
    if zipfile.is_zipfile(file_path):
        try:
            with zipfile.ZipFile(file_path, 'r') as z:
                xml_file = None
                for name in z.namelist():
                    if name.endswith("document.xml"):
                        xml_file = name
                        break
                if not xml_file:
                    raise ValueError("Arquivo ZIP sem document.xml.")
                with z.open(xml_file) as f:
                    return parse_silhouette_xml(f.read())
        except zipfile.BadZipFile:
            raise ValueError("Arquivo .studio3 inválido ou corrompido.")
        except Exception as e:
            app.logger.error(f"Erro inesperado ao abrir ZIP: {e}")
            raise

    # Caso contrário, tenta abrir como XML direto (ex: .studio v2 ou .gsp)
    try:
        with open(file_path, 'rb') as f:
            return parse_silhouette_xml(f.read())
    except Exception as e:
        raise ValueError(
            "Este arquivo não é suportado. Se foi salvo no Silhouette Studio V5, "
            "tente exportar como .studio (V2) ou .gsp para ser compatível."
        )

@app.route('/convert', methods=['POST'])
def convert_file():
    if 'file' not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    file = request.files['file']
    filename = file.filename.lower()

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        file.save(tmp.name)
        temp_path = tmp.name

    try:
        # Agora aceita também .studio (v2) e .gsp
        if filename.endswith((".studio3", ".studio", ".gsp")):
            try:
                svg_data = silhouette_to_svg(temp_path)
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
            return jsonify({"error": "Formato inválido. Envie .studio3, .studio, .gsp, .svg ou .dxf"}), 400

    except Exception as e:
        os.unlink(temp_path)
        app.logger.error(f"Erro interno no servidor: {e}")
        return jsonify({"error": "Erro interno no servidor"}), 500

@app.route('/', methods=['GET'])
def home():
    return "API de conversão para arquivos Silhouette Studio (.studio3, .studio, .gsp) → SVG está ativa."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
