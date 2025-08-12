from flask import Flask, request, send_file, jsonify
import subprocess
import tempfile
import os
import shutil
import sys
import math
import zipfile
import logging
from io import BytesIO

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# Найдем путь к zint
ZINT_PATH = shutil.which('zint') or '/usr/bin/zint'
logger.info(f"Using Zint path: {ZINT_PATH}")

# Сопоставление форматов файлов с MIME-типами
MIME_TYPES = {
    'BMP': 'image/bmp',
    'EMF': 'image/emf',
    'EPS': 'application/postscript',
    'GIF': 'image/gif',
    'PCX': 'image/vnd.zbrush.pcx',
    'PNG': 'image/png',
    'SVG': 'image/svg+xml',
    'TIF': 'image/tiff',
    'TXT': 'text/plain'
}

@app.route('/generate_batch', methods=['POST'])
def generate_batch():
    """Пакетная генерация штрихкодов с использованием batch-режима Zint"""
    try:
        # Проверяем заголовок Content-Type
        if not request.is_json:
            return jsonify({
                "error": "Unsupported Media Type",
                "message": "Content-Type must be application/json"
            }), 415
        
        # Получаем JSON
        request_data = request.get_json()
        if not request_data or not isinstance(request_data, dict):
            return jsonify({
                "error": "Bad Request",
                "message": "Invalid JSON data. Expecting object with parameters"
            }), 400
        
        logger.info(f"Received batch request with {len(request_data.get('items', []))} items")
        
        # Извлекаем параметры
        items = request_data.get('items', [])
        common_params = request_data.get('common', {})
        
        if not items:
            return jsonify({"error": "Bad Request", "message": "No items provided"}), 400
        
        # Проверяем, что items - это список строк
        if not all(isinstance(item, str) for item in items):
            return jsonify({
                "error": "Bad Request",
                "message": "All items must be strings"
            }), 400
        
        # Создаем временную директорию для работы
        with tempfile.TemporaryDirectory() as temp_dir:
            # Создаем входной файл для Zint
            input_path = os.path.join(temp_dir, 'input.txt')
            with open(input_path, 'w', encoding='utf-8') as f:
                for item in items:
                    f.write(item + '\n')  # Каждая строка - отдельный штрихкод
            
            # Определяем параметры генерации
            filetype = common_params.get('filetype', 'PNG').upper()
            barcode_type = common_params.get('type', '71')
            scale = common_params.get('scale', 2)
            output_pattern = common_params.get('output_pattern', 'barcode_')
            
            # Определяем количество тильд для нумерации
            num_digits = max(3, math.ceil(math.log10(len(items) + 1)))
            tilde_str = '~' * num_digits
            
            # Формируем шаблон выходного файла
            output_template = os.path.join(temp_dir, f"{output_pattern}{tilde_str}.{filetype.lower()}")
            
            # Собираем команду Zint
            cmd = [
                ZINT_PATH,
                '--batch',
                '--barcode', str(barcode_type),
                '--filetype', filetype,
                '--output', output_template,
                '--input', input_path,
                '--scale', str(scale)
            ]
            
            # Добавляем общие параметры
            for param, value in common_params.items():
                if param in ['type', 'filetype', 'scale', 'output_pattern']:
                    continue  # Уже обработаны
                
                # Булевые параметры (флаги)
                if isinstance(value, bool) and value:
                    cmd.append(f'--{param}')
                # Параметры со значениями
                elif not isinstance(value, bool):
                    cmd.extend([f'--{param}', str(value)])
            
            logger.info(f"Executing command: {' '.join(cmd)}")
            
            # Выполняем команду
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            # Логируем вывод Zint
            if result.stdout:
                logger.info(f"Zint stdout: {result.stdout}")
            if result.stderr:
                logger.error(f"Zint stderr: {result.stderr}")
            
            if result.returncode != 0:
                error_msg = f"Zint batch error ({result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
                return jsonify({"error": "Barcode generation failed", "details": error_msg}), 500
            
            # Собираем сгенерированные файлы
            generated_files = []
            for i in range(1, len(items) + 1):
                # Форматируем номер с ведущими нулями
                num_str = str(i).zfill(num_digits)
                filename = f"{output_pattern}{num_str}.{filetype.lower()}"
                file_path = os.path.join(temp_dir, filename)
                
                if os.path.exists(file_path):
                    generated_files.append(file_path)
                else:
                    logger.warning(f"Missing output file: {file_path}")
            
            # Создаем ZIP-архив
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for file_path in generated_files:
                    arcname = os.path.basename(file_path)
                    zip_file.write(file_path, arcname)
                    logger.info(f"Added to ZIP: {arcname}")
            
            zip_buffer.seek(0)
            return send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name='barcodes.zip'
            )
    
    except Exception as e:
        logger.exception("Unexpected error in generate_batch")
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500

@app.route('/generate', methods=['GET', 'POST'])
def generate_single():
    """Генерация одного штрихкода (поддержка GET и POST)"""
    try:
        # Определяем параметры в зависимости от метода запроса
        if request.method == 'POST':
            # Для POST - извлекаем JSON из тела запроса
            params = request.get_json() or {}
        else:
            # Для GET - параметры из query string
            params = request.args.to_dict()
        
        logger.info(f"Received generation request via {request.method}")

        # Обработка данных - замена квадратных скобок на круглые
        data = params.get('data', '')
        #if '[' in data or ']' in data:
        #    data = data.replace('[', '(').replace(']', ')')
        #    logger.info("Replaced square brackets with parentheses in GS1 data")
        
        # Определяем формат файла
        filetype = params.get('filetype', 'PNG').upper()
        mime_type = MIME_TYPES.get(filetype, 'application/octet-stream')

        # Создаем временный файл для вывода
        with tempfile.NamedTemporaryFile(suffix=f".{filetype}", delete=False) as tmp:
            output_path = tmp.name
        
        # Базовые параметры команды
        cmd = [
            ZINT_PATH,
            '--data', data,
            '--filetype', filetype,
            '-o', output_path
        ]
        
        # Добавляем тип штрихкода (обязательный параметр)
        barcode_type = params.get('type', '58')
        cmd.extend(['--barcode', str(barcode_type)])
        
        # Обрабатываем все остальные параметры
        for key, value in params.items():
            # Пропускаем уже обработанные параметры
            if key in ['data', 'filetype', 'type']:
                continue
            
            # Для GET-запросов: булевы параметры без значения
            if request.method == 'GET' and value == '':
                cmd.append(f'--{key}')
            # Для POST-запросов: булевы параметры как true/false
            elif request.method == 'POST' and isinstance(value, bool) and value:
                cmd.append(f'--{key}')
            # Для POST-запросов: булевы параметры как строки
            elif request.method == 'POST' and isinstance(value, str) and value.lower() in ['true', '1', 'yes']:
                cmd.append(f'--{key}')
            # Числовые/строковые параметры
            else:
                cmd.extend([f'--{key}', str(value)])
        
        logger.info(f"Command: {' '.join(cmd)}")
        
        # Выполняем команду
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            error_msg = f"Zint error ({result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
            logger.error(error_msg)
            return jsonify({"error": "Barcode generation failed", "details": error_msg}), 400
        
        # Отправляем файл
        response = send_file(output_path, mimetype=mime_type)
        
        # Удаляем временный файл
        os.unlink(output_path)
        return response
    
    except Exception as e:
        logger.exception("Unexpected error in generate_single")
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Проверка работоспособности сервиса"""
    return jsonify({"status": "ok", "zint": ZINT_PATH})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)