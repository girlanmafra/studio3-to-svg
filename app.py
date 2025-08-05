import zipfile
import xml.etree.ElementTree as ET
import re
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import tempfile
import os
from io import BytesIO
from xml.sax.saxutils import escape
from svg.path import parse_path, Path
from svg.path.util import get_size

app = Flask(__name__)
# Permitir requisições de qualquer origem (necessário para o front-end em outro domínio)
CORS(app)

def remove_namespace(tag):
    """
    Remove o namespace do elemento XML.
    """
    return tag.split('}')[-1] if '}' in tag else tag

def calcular_viewbox(svg_paths):
    """
    Calcula dinamicamente a viewBox e as dimensões do SVG com base
    nas coordenadas de todos os caminhos.
    """
    all_paths = [parse_path(p.split('d="')[1].split('"')[0]) for p in svg_paths]
    
    if not all_paths:
        return 0, 0, 100, 100 # Default fallback

    # Use a biblioteca svg.path para calcular o bounding box
    min_x, min_y, max_x, max_y = float('inf'), float('inf'), float('-inf'), float('-inf')

    for p in all_paths:
        try:
            size_min_x, size_min_y, size_max_x, size_max_y = get_size(p)
            min_x = min(min_x, size_min_x)
            min_y = min(min_y, size_min_y)
            max_x = max(max_x, size_max_x)
            max_y = max(max_y, size_max_y)
        except Exception:
            continue

    width = max_x - min_x
    height = max_y - min_y

    return min_x, min_y, width, height

def gerar_svg(svg_paths):
    """
    Monta o SVG final com medidas dinâmicas.
    """
    min_x, min_y, width, height = calcular_viewbox(svg_paths)

    svg_content = f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg xmlns="http://www.w3.org/2000/svg"
     version="1.1"
     width="{width:.2f}mm" height="{height:.2f}mm"
     viewBox="{min_x:.2f} {min_y:.2f} {width:.2f} {height:.2f}"
     xmlns:xlink="http://www.w3.org/1999/xlink">
{''.join(svg_paths)}
</svg>
"""
    return svg_content

def studio3_to_svg(studio3_path):
    """
    Processa arquivos .studio3 no formato ZIP.
    """
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
                if tag == 'path':
                    d = elem.attrib.get('d')
                    if d:
                        svg_paths.append(f'<path d="{escape(d)}" fill="none" stroke="black" stroke-width="1"/>')
                elif tag == 'polyline':
                    points = elem.attrib.get('points')
                    if points:
                        # Converte polyline points para o atributo 'd' do path
                        path_d = 'M' + points.replace(' ', ' L')
                        svg_paths.append(f'<path d="{escape(path_d)}" fill="none" stroke="black" stroke-width="1"/>')
                elif tag == 'line':
                    x1 = elem.attrib.get('x1', '0')
                    y1 = elem.attrib.get('y1', '0')
                    x2 = elem.attrib.get('x2', '0')
                    y2 = elem.attrib.get('y2', '0')
                    path_d = f'M{x1} {y1} L{x2} {y2}'
                    svg_paths.append(f'<path d="{escape(path_d)}" fill="none" stroke="black" stroke-width="1"/>')

            if not svg_paths:
                raise ValueError("Nenhum path válido encontrado no document.xml")

            return gerar_svg(svg_paths)

    except zipfile.BadZipFile:
        raise ValueError("O arquivo não é um formato ZIP válido. Pode ser um arquivo .studio3 V5+ (binário) que não é suportado por este conversor.")

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
        return jsonify({"error": f"Erro interno no servidor: {str(e)}"}), 500

@app.route('/', methods=['GET'])
def home():
    # Mensagem de status simples para confirmar que a API está funcionando
    return jsonify({"status": "API de conversão .studio3 para .svg funcionando."})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
