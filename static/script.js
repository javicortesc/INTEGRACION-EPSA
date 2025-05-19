document.addEventListener('DOMContentLoaded', () => {
    const avisoCamionForm = document.getElementById('avisoCamionForm');
    const statusMessagesDiv = document.getElementById('statusMessages');
    
    const currentIngresoIdSpan = document.getElementById('currentIngresoId');
    const currentLicencePlateSpan = document.getElementById('currentLicencePlate');
    const currentContainerIdSpan = document.getElementById('currentContainerId');
    const currentEpsaStatusSpan = document.getElementById('currentEpsaStatus');
    const currentEpsaMessageSpan = document.getElementById('currentEpsaMessage');

    const confirmarSalidaBtn = document.getElementById('confirmarSalidaBtn');
    const eliminarAvisoBtn = document.getElementById('eliminarAvisoBtn');

    let currentAccessToken = null;
    let currentIngresoId = null;
    let pollingInterval = null;

    const API_BASE_URL = ''; // Flask serves on same origin

    // --- Helper Functions ---
    function logMessage(message, type = 'info') {
        const p = document.createElement('p');
        p.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
        p.className = `status-${type}`; // Corresponds to CSS classes
        statusMessagesDiv.insertBefore(p, statusMessagesDiv.firstChild); // Add to top
        console.log(`[${type.toUpperCase()}] ${message}`);
    }

    function getCurrentTimestamp() {
        return new Date().toISOString();
    }

    function updateTruckInfoDisplay(data = null) {
        if (data) {
            currentIngresoIdSpan.textContent = data.ingresoId || currentIngresoId || '-';
            currentLicencePlateSpan.textContent = data.licencePlate || '-';
            currentContainerIdSpan.textContent = data.containerId || '-';
            
            let statusText = 'Desconocido';
            if (data.isAuthorized === true) statusText = 'AUTORIZADO';
            else if (data.isAuthorized === false) statusText = 'RECHAZADO';
            else if (data.isAuthorized === null || data.message?.includes('Procesando')) statusText = 'PENDIENTE DE AUTORIZACIÓN';
            else if (data.status === 'DEPARTED') statusText = 'CAMIÓN SALIÓ';
            else if (data.status === 'DELETED_AVISO') statusText = 'AVISO ELIMINADO';


            currentEpsaStatusSpan.textContent = statusText;
            currentEpsaMessageSpan.textContent = data.message || '-';
        } else {
            currentIngresoIdSpan.textContent = '-';
            currentLicencePlateSpan.textContent = '-';
            currentContainerIdSpan.textContent = '-';
            currentEpsaStatusSpan.textContent = '-';
            currentEpsaMessageSpan.textContent = '-';
        }
    }
    
    function resetUIForNewAviso() {
        logMessage("Listo para nuevo aviso.", "info");
        updateTruckInfoDisplay(); // Clear display
        confirmarSalidaBtn.disabled = true;
        eliminarAvisoBtn.disabled = true;
        currentIngresoId = null;
        if (pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
        }
    }

    // --- API Call Functions ---
    async function getEpsaToken() {
        try {
            const response = await fetch(`${API_BASE_URL}/epsa/auth/getToken`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    // Basic Auth would be set by browser if endpoint required it, or use Authorization header
                },
                body: new URLSearchParams({
                    'grant_type': 'client_credentials'
                    // 'client_id': 'YOUR_CLIENT_ID', // If needed
                    // 'client_secret': 'YOUR_CLIENT_SECRET' // If needed
                })
            });
            const data = await response.json();
            if (data.isSuccess && data.value && data.value.accessToken) {
                currentAccessToken = data.value.accessToken;
                logMessage("Token de EPSA obtenido con éxito.", "success");
                return true;
            } else {
                logMessage(`Error al obtener token: ${JSON.stringify(data.errors) || 'Respuesta inesperada'}`, "error");
                currentAccessToken = null;
                return false;
            }
        } catch (error) {
            logMessage(`Excepción al obtener token: ${error.message}`, "error");
            currentAccessToken = null;
            return false;
        }
    }

    async function enviarAvisoASAT(formData) {
        if (!currentAccessToken) {
            logMessage("No hay token de acceso. Intentando obtener uno nuevo.", "warning");
            if (!await getEpsaToken()) {
                logMessage("Fallo al obtener nuevo token. No se puede enviar aviso.", "error");
                return;
            }
        }

        const payload = {
            licencePlate: formData.get('licencePlate'),
            containerId: formData.get('containerId'),
            isocode: formData.get('isocode'),
            timestamp: getCurrentTimestamp()
        };

        try {
            logMessage(`Enviando aviso a EPSA para ${payload.licencePlate}...`, "info");
            const response = await fetch(`${API_BASE_URL}/epsa/aviso_camion_listo`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${currentAccessToken}`
                },
                body: JSON.stringify(payload)
            });
            const data = await response.json();

            if (response.ok && data.isSuccess && data.value) {
                currentIngresoId = data.value;
                logMessage(`Aviso enviado. ID de Ingreso EPSA: ${currentIngresoId}. Esperando autorización...`, "success");
                updateTruckInfoDisplay({
                    ingresoId: currentIngresoId,
                    licencePlate: payload.licencePlate,
                    containerId: payload.containerId,
                    isocode: payload.isocode,
                    isAuthorized: null, // Pending
                    message: "Aviso enviado, esperando autorización de ASAT."
                });
                eliminarAvisoBtn.disabled = false;
                startPollingStatus(currentIngresoId);
            } else {
                logMessage(`Error de EPSA al enviar aviso: ${data.errors ? data.errors[0].errorMessage : (data.title || 'Error desconocido')}`, "error");
                updateTruckInfoDisplay();
            }
        } catch (error) {
            logMessage(`Excepción al enviar aviso: ${error.message}`, "error");
            updateTruckInfoDisplay();
        }
    }

    function startPollingStatus(ingresoId) {
        if (pollingInterval) {
            clearInterval(pollingInterval);
        }
        logMessage(`Iniciando sondeo de estado para ID: ${ingresoId}`, "info");
        
        // Immediate check
        checkAuthorizationStatus(ingresoId); 

        pollingInterval = setInterval(() => {
            checkAuthorizationStatus(ingresoId);
        }, 5000); // Poll every 5 seconds
    }

    async function checkAuthorizationStatus(ingresoId) {
        if (!currentAccessToken) {
            logMessage("No hay token para consultar estado. Intentando obtener...", "warning");
            if (!await getEpsaToken()) return; // Stop if token fails
        }
        if (!ingresoId) {
            logMessage("No hay ID de ingreso para consultar.", "warning");
            if (pollingInterval) clearInterval(pollingInterval);
            return;
        }

        logMessage(`Consultando estado a EPSA para ID: ${ingresoId}...`, "info");
        try {
            const response = await fetch(`${API_BASE_URL}/epsa/consulta_estado/${ingresoId}`, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${currentAccessToken}`
                }
            });
            const data = await response.json();

            if (response.ok && data.isSuccess && data.value) {
                const statusData = data.value;
                statusData.ingresoId = ingresoId; // Add it for consistency
                updateTruckInfoDisplay(statusData);

                if (statusData.isAuthorized === true) {
                    logMessage(`¡AUTORIZADO! Mensaje: ${statusData.message}`, "success");
                    confirmarSalidaBtn.disabled = false;
                    eliminarAvisoBtn.disabled = true; // Can't delete if authorized
                    if (pollingInterval) clearInterval(pollingInterval);
                } else if (statusData.isAuthorized === false) {
                    logMessage(`RECHAZADO. Mensaje: ${statusData.message}`, "error");
                    confirmarSalidaBtn.disabled = true;
                    eliminarAvisoBtn.disabled = false; // Can delete if rejected
                    if (pollingInterval) clearInterval(pollingInterval);
                } else {
                    logMessage(`Estado pendiente. Mensaje: ${statusData.message || 'Procesando...'}`, "info");
                    // Polling continues
                }
            } else {
                 logMessage(`Error de EPSA al consultar estado: ${data.errors ? data.errors[0].errorMessage : (data.title || 'Error desconocido')}`, "error");
                if (pollingInterval) clearInterval(pollingInterval); // Stop polling on error
            }
        } catch (error) {
            logMessage(`Excepción al consultar estado: ${error.message}`, "error");
            if (pollingInterval) clearInterval(pollingInterval); // Stop polling on error
        }
    }

    async function confirmarSalida() {
        if (!currentIngresoId) {
            logMessage("No hay ID de ingreso para confirmar salida.", "error");
            return;
        }
        if (!currentAccessToken) {
            logMessage("No hay token para confirmar salida. Intentando obtener...", "warning");
            if (!await getEpsaToken()) return;
        }
        
        logMessage(`Confirmando salida a EPSA para ID: ${currentIngresoId}...`, "info");
        const payload = {
            id: currentIngresoId,
            timestamp: getCurrentTimestamp()
        };

        try {
            const response = await fetch(`${API_BASE_URL}/epsa/salida_extraportuario`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${currentAccessToken}`
                },
                body: JSON.stringify(payload)
            });
            const data = await response.json();

            if (response.ok && data.isSuccess) {
                logMessage("Salida confirmada con éxito a EPSA.", "success");
                updateTruckInfoDisplay({
                    ...getCurrentTruckDataFromUI(), // Keep previous data
                    status: 'DEPARTED',
                    message: 'Camión ha salido del extraportuario.'
                });
                confirmarSalidaBtn.disabled = true;
                eliminarAvisoBtn.disabled = true;
            } else {
                logMessage(`Error de EPSA al confirmar salida: ${data.errors ? data.errors[0].errorMessage : (data.title || 'Error desconocido')}`, "error");
            }
        } catch (error) {
            logMessage(`Excepción al confirmar salida: ${error.message}`, "error");
        }
    }
    
    async function eliminarAviso() {
        if (!currentIngresoId) {
            logMessage("No hay ID de ingreso para eliminar aviso.", "error");
            return;
        }
         if (!currentAccessToken) {
            logMessage("No hay token para eliminar aviso. Intentando obtener...", "warning");
            if (!await getEpsaToken()) return;
        }

        if (!confirm("¿Está seguro de que desea eliminar este aviso de ingreso? Esta acción es opcional y generalmente se usa si el camión ya no irá a puerto.")) {
            return;
        }

        logMessage(`Solicitando eliminación de aviso a EPSA para ID: ${currentIngresoId}...`, "info");
        try {
            const response = await fetch(`${API_BASE_URL}/epsa/eliminar_ingreso/${currentIngresoId}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${currentAccessToken}`
                }
            });
            const data = await response.json(); // EPSA returns JSON for DELETE success/error too

            if (response.ok && data.isSuccess) {
                logMessage("Aviso eliminado con éxito en EPSA.", "success");
                 updateTruckInfoDisplay({
                    ...getCurrentTruckDataFromUI(),
                    status: 'DELETED_AVISO',
                    message: 'Aviso de ingreso eliminado por el extraportuario.'
                });
                if (pollingInterval) clearInterval(pollingInterval);
                confirmarSalidaBtn.disabled = true;
                eliminarAvisoBtn.disabled = true;
            } else {
                 logMessage(`Error de EPSA al eliminar aviso: ${data.errors ? data.errors[0].errorMessage : (data.title || 'Error desconocido')}`, "error");
            }
        } catch (error) {
            logMessage(`Excepción al eliminar aviso: ${error.message}`, "error");
        }
    }
    
    function getCurrentTruckDataFromUI() {
        return {
            ingresoId: currentIngresoIdSpan.textContent,
            licencePlate: currentLicencePlateSpan.textContent,
            containerId: currentContainerIdSpan.textContent,
            // isAuthorized and message will be updated by new status
        };
    }


    // --- Event Listeners ---
    avisoCamionForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        resetUIForNewAviso(); // Prepare for a new submission flow
        const formData = new FormData(avisoCamionForm);
        await enviarAvisoASAT(formData);
    });

    confirmarSalidaBtn.addEventListener('click', confirmarSalida);
    eliminarAvisoBtn.addEventListener('click', eliminarAviso);

    // Initial token fetch
    getEpsaToken();
    resetUIForNewAviso(); // Set initial state
});