from flask import Flask, render_template, request, jsonify
import uuid
import time
import random
from datetime import datetime, timezone

app = Flask(__name__)

# In-memory "database" to store truck statuses
# key: ingreso_id
# value: { 'licencePlate': ..., 'containerId': ..., 'isocode': ...,
# 'timestamp_aviso': ..., 'status': 'PENDING_AUTH' | 'AUTHORIZED' | 'REJECTED' | 'DEPARTED',
# 'message': ..., 'auth_timestamp': ... }
truck_data_store = {}

# --- Helper Functions ---
def get_current_timestamp_iso():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')

# --- Simulated EPSA/ASAT Endpoints ---
@app.route('/epsa/auth/getToken', methods=['POST'])
def get_token():
    # In a real scenario, validate client_id and client_secret from Basic Auth
    # For simulation, we just return a dummy token
    # request.authorization.username / request.authorization.password
    if request.form.get('grant_type') == 'client_credentials':
        return jsonify({
            "value": {
                "accessToken": "SIMULATED_ACCESS_TOKEN_" + str(uuid.uuid4()),
                "tokenType": "Bearer",
                "expiresIn": 3600  # 1 hour
            },
            "isSuccess": True,
            "isFailure": False,
            "errors": None
        })
    return jsonify({
        "type": "https://tools.ietf.org/html/rfc7231#section-6.5.1",
        "title": "Bad Request",
        "status": 400,
        "isSuccess": False,
        "isFailure": True,
        "errors": [{"propertyName": "grant_type", "errorMessage": "unsupported_grant_type"}]
    }), 400

@app.route('/epsa/aviso_camion_listo', methods=['POST'])
def epsa_aviso_camion_listo():
    # Simulate token check - normally done via a decorator or middleware
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer SIMULATED_ACCESS_TOKEN_'):
        return jsonify({"title": "Unauthorized", "status": 401}), 401

    data = request.json
    licence_plate = data.get('licencePlate')
    container_id = data.get('containerId')
    isocode = data.get('isocode')
    # timestamp = data.get('timestamp') # Client timestamp

    if not all([licence_plate, container_id, isocode]):
        return jsonify({
            "title": "Validation Failure", "status": 400, "isSuccess": False, "isFailure": True,
            "errors": [{"propertyName": "Request", "errorMessage": "Missing required fields"}]
        }), 400

    # Check for duplicates (simplified)
    for entry in truck_data_store.values():
        if entry['licencePlate'] == licence_plate and entry['status'] not in ['DEPARTED', 'REJECTED', 'DELETED_AVISO']:
            return jsonify({
                "title": "Validation Failure", "status": 400, "isSuccess": False, "isFailure": True,
                "errors": [{"propertyName": "LicencePlate", "errorMessage": "El camión ya está en el sistema"}]
            }), 400
        if entry['containerId'] == container_id and entry['status'] not in ['DEPARTED', 'REJECTED', 'DELETED_AVISO']:
             return jsonify({
                "title": "Validation Failure", "status": 400, "isSuccess": False, "isFailure": True,
                "errors": [{"propertyName": "Containers[0]", "errorMessage": "El contenedor que está intentando insertar, ya existe en el sistema"}]
            }), 400


    ingreso_id = str(uuid.uuid4())
    truck_data_store[ingreso_id] = {
        'licencePlate': licence_plate,
        'containerId': container_id,
        'isocode': isocode,
        'timestamp_aviso': get_current_timestamp_iso(),
        'status': 'PENDING_AUTH', # Status indicating waiting for authorization
        'message': 'Aviso recibido, esperando autorización de ASAT.',
        'auth_timestamp': None
    }

    app.logger.info(f"EPSA: Aviso camión listo recibido for ID {ingreso_id}: {truck_data_store[ingreso_id]}")

    # Simulate ASAT processing and sending notification back to Extraportuario
    # In a real system, ASAT would make an HTTP call to /extraportuario/notificacion
    # Here, we'll simulate it by directly updating the status after a delay
    # This is a simplification for the simulation.
    # A more robust simulation would use a background thread or task queue.
    
    # ---- START SIMULATED ASAT INTERNAL PROCESSING & NOTIFICATION ----
    # This part simulates ASAT taking some time and then deciding.
    # It's NOT part of the EPSA endpoint response itself, but an action EPSA/ASAT takes.
    def simulate_asat_decision_and_notify(current_ingreso_id):
        with app.app_context(): # Needed if this were in a separate thread using app features
            time.sleep(random.randint(3, 8)) # Simulate processing time
            
            if current_ingreso_id not in truck_data_store or truck_data_store[current_ingreso_id]['status'] != 'PENDING_AUTH':
                app.logger.warning(f"ASAT Sim: Ingreso {current_ingreso_id} no longer PENDING_AUTH. Aborting notification.")
                return

            authorized = random.choice([True, True, False]) # Higher chance of being authorized
            notification_message = ""
            if authorized:
                truck_data_store[current_ingreso_id]['status'] = 'AUTHORIZED'
                notification_message = "Puede salir a puerto"
                app.logger.info(f"ASAT Sim: Ingreso {current_ingreso_id} AUTORIZADO.")
            else:
                truck_data_store[current_ingreso_id]['status'] = 'REJECTED'
                reasons = ["Sin preaviso del conductor", "Visación en terminal pendiente", "Límite de camiones en nodo alcanzado"]
                notification_message = random.choice(reasons)
                app.logger.info(f"ASAT Sim: Ingreso {current_ingreso_id} RECHAZADO. Razón: {notification_message}")

            truck_data_store[current_ingreso_id]['message'] = notification_message
            truck_data_store[current_ingreso_id]['auth_timestamp'] = get_current_timestamp_iso()
            
            # This is where the REAL ASAT would make an HTTP call to /extraportuario/notificacion
            # For our simulation, the client will poll /epsa/consulta_estado
            # We can log what would have been sent:
            notification_payload = {
                "id": current_ingreso_id,
                "isAuthorized": authorized,
                "message": notification_message,
                "timestamp": get_current_timestamp_iso()
            }
            app.logger.info(f"ASAT Sim: Prepared notification for Extraportuario: {notification_payload}")
            # In a real inter-system call:
            # try:
            #   requests.post('URL_OF_EXTRAPORTUARIO/extraportuario/notificacion', json=notification_payload, timeout=5)
            # except requests.RequestException as e:
            #   app.logger.error(f"ASAT Sim: Failed to send notification to Extraportuario for {current_ingreso_id}: {e}")

    # For simplicity, run this in a blocking way for the simulation.
    # In a real Flask app, this should be offloaded to a background worker (e.g., Celery, RQ, or threading).
    # For this single-user demo, a direct call after response is fine, or threading for non-blocking.
    # Let's use threading to make it non-blocking for the /epsa/aviso_camion_listo response.
    import threading
    thread = threading.Thread(target=simulate_asat_decision_and_notify, args=(ingreso_id,))
    thread.start()
    # ---- END SIMULATED ASAT INTERNAL PROCESSING & NOTIFICATION ----

    return jsonify({
        "value": ingreso_id,
        "isSuccess": True,
        "isFailure": False,
        "errors": None
    })

@app.route('/epsa/consulta_estado/<string:ingreso_id>', methods=['GET'])
def epsa_consulta_estado(ingreso_id):
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer SIMULATED_ACCESS_TOKEN_'):
        return jsonify({"title": "Unauthorized", "status": 401}), 401

    truck_info = truck_data_store.get(ingreso_id)
    if not truck_info:
        return jsonify({
            "title": "Validation Failure", "status": 400, "isSuccess": False, "isFailure": True,
            "errors": [{"propertyName": "Id", "errorMessage": "No se encontró el ingreso en el sistema"}]
        }), 400

    # Construct response based on stored status
    response_value = {
        "licencePlate": truck_info['licencePlate'],
        "containerId": truck_info['containerId'],
        "isocode": truck_info.get('isocode', ''), # Added in modification
        "isAuthorized": truck_info['status'] == 'AUTHORIZED',
        "message": truck_info['message'],
        "timestamp": truck_info.get('auth_timestamp') or truck_info['timestamp_aviso']
    }
    if truck_info['status'] == 'PENDING_AUTH': # Not yet processed by simulated ASAT
        response_value["isAuthorized"] = None # Or some other indicator of pending
        response_value["message"] = "Procesando autorización..."

    return jsonify({
        "value": response_value,
        "isSuccess": True,
        "isFailure": False,
        "errors": None
    })

@app.route('/epsa/salida_extraportuario', methods=['POST'])
def epsa_salida_extraportuario():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer SIMULATED_ACCESS_TOKEN_'):
        return jsonify({"title": "Unauthorized", "status": 401}), 401

    data = request.json
    ingreso_id = data.get('id')
    # timestamp = data.get('timestamp') # Client timestamp

    truck_info = truck_data_store.get(ingreso_id)
    if not truck_info:
        return jsonify({
            "title": "Validation Failure", "status": 400, "isSuccess": False, "isFailure": True,
            "errors": [{"propertyName": "Id", "errorMessage": "No se encontró el ingreso en el sistema"}]
        }), 400

    if truck_info['status'] != 'AUTHORIZED':
        return jsonify({
            "title": "Validation Failure", "status": 400, "isSuccess": False, "isFailure": True,
            "errors": [{"propertyName": "State", "errorMessage": "El camión no está autorizado para salir o ya salió."}]
        }), 400

    truck_data_store[ingreso_id]['status'] = 'DEPARTED'
    truck_data_store[ingreso_id]['message'] = 'Camión ha salido del extraportuario.'
    truck_data_store[ingreso_id]['departure_timestamp'] = get_current_timestamp_iso()
    app.logger.info(f"EPSA: Salida de extraportuario confirmada para ID {ingreso_id}")

    return jsonify({
        "value": "fc65b51b-e3b3-4129-96b4-487008dd27a1", # Dummy success value
        "isSuccess": True,
        "isFailure": False,
        "errors": None
    })

@app.route('/epsa/eliminar_ingreso/<string:ingreso_id>', methods=['DELETE'])
def epsa_eliminar_ingreso(ingreso_id):
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer SIMULATED_ACCESS_TOKEN_'):
        return jsonify({"title": "Unauthorized", "status": 401}), 401

    truck_info = truck_data_store.get(ingreso_id)
    if not truck_info:
        return jsonify({
            "title": "Validation Failure", "status": 400, "isSuccess": False, "isFailure": True,
            "errors": [{"propertyName": "Id", "errorMessage": "No se encontró el ingreso en el sistema"}]
        }), 400
    
    # Document implies can only delete if not authorized after X time.
    # For simplicity, allow deletion if not DEPARTED.
    if truck_info['status'] == 'DEPARTED':
        return jsonify({
            "title": "Validation Failure", "status": 400, "isSuccess": False, "isFailure": True,
            "errors": [{"propertyName": "State", "errorMessage": "No se puede eliminar un aviso de un camión que ya salió."}]
        }), 400

    # Instead of full deletion, mark as deleted for audit/review
    truck_data_store[ingreso_id]['status'] = 'DELETED_AVISO'
    truck_data_store[ingreso_id]['message'] = 'Aviso de ingreso eliminado por el extraportuario.'
    truck_data_store[ingreso_id]['deletion_timestamp'] = get_current_timestamp_iso()
    app.logger.info(f"EPSA: Aviso de ingreso eliminado para ID {ingreso_id}")
    
    return jsonify({
        "isSuccess": True,
        "isFailure": False,
        "errors": None
    }) # 200 OK or 204 No Content is also fine for DELETE

# --- Actual Extraportuario Endpoint (called by EPSA/ASAT) ---
@app.route('/extraportuario/notificacion', methods=['POST'])
def extraportuario_recibir_notificacion():
    data = request.json
    ingreso_id = data.get('id')
    is_authorized = data.get('isAuthorized')
    message = data.get('message')
    timestamp = data.get('timestamp')

    app.logger.info(f"EXTRAPORTUARIO: Notificación RECIBIDA de ASAT: ID={ingreso_id}, Auth={is_authorized}, Msg='{message}', Time={timestamp}")

    if ingreso_id in truck_data_store:
        if is_authorized:
            truck_data_store[ingreso_id]['status'] = 'AUTHORIZED'
        else:
            truck_data_store[ingreso_id]['status'] = 'REJECTED'
        truck_data_store[ingreso_id]['message'] = message
        truck_data_store[ingreso_id]['auth_timestamp'] = timestamp
        app.logger.info(f"EXTRAPORTUARIO: Estado actualizado para {ingreso_id} a {truck_data_store[ingreso_id]['status']}")
    else:
        app.logger.warning(f"EXTRAPORTUARIO: Notificación recibida para ID desconocido: {ingreso_id}")
        # Could return an error, but spec says "Se sugiere algún campo booleano y un mensaje."
        return jsonify({"received": False, "message": "ID de ingreso no encontrado"}), 404


    # Response from Extraportuario to ASAT, as per page 12
    return jsonify({"received": True, "message": "Notificación procesada correctamente por el extraportuario."})


# --- Frontend Route ---
@app.route('/')
def index():
    return render_template('index.html', app_version="Mayo 2025 – Versión 2 Sim")

if __name__ == '__main__':
    app.run(debug=True, port=5000)