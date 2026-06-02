import os
import requests
from bs4 import BeautifulSoup
import time
import random
import logging

# Настройка логирования для удобного вывода
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

PHPSESSID = os.getenv("PHPSESSID")
BASE_URL = "https://www.steamgifts.com"
TARGET_PAGE_URL = "https://www.steamgifts.com/giveaways/search?&type=wishlist"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
    "Referer": BASE_URL,
    "X-Requested-With": "XMLHttpRequest",
}

def init_session():
    session = requests.Session()
    session.cookies.set("PHPSESSID", PHPSESSID, domain=".steamgifts.com")
    session.headers.update(HEADERS)
    return session

def get_xsrf_token(session):
    """Получение CSRF токена из cookies (самый надежный способ на SG)"""
    response = session.get(BASE_URL)
    if response.status_code == 200:
        xsrf = session.cookies.get("xsrf_token")
        if xsrf:
            return xsrf
    logging.error("Не удалось получить xsrf_token. Проверьте валидность PHPSESSID.")
    return None

def extract_giveaways(session, url):
    """Парсинг активных раздач, в которых мы еще не участвуем"""
    giveaways = []
    response = session.get(url)
    
    if response.status_code != 200:
        logging.error(f"Ошибка загрузки страницы: {response.status_code}")
        return giveaways

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Ищем ссылки на раздачи внутри заголовков
    giveaway_links = soup.select('a.giveaway__heading__name[href^="/giveaway/"]')
    
    for link in giveaway_links:
        href = link.get('href')
        # Извлекаем код раздачи из URL вида /giveaway/CODE/name
        code = href.split('/')[2] 
        
        # Проверяем, не участвуем ли мы уже (ищем родительский элемент с классом is_faded)
        parent_row = link.find_parent('div', class_=lambda c: c and 'giveaway__row__outer-wrap' in c)
        if parent_row and 'is_faded' in parent_row.get('class', []):
            logging.info(f"Пропуск (уже участвуем или завершена): {code}")
            continue
            
        giveaways.append(code)
                
    return giveaways

def join_giveaway(session, xsrf_token, code):
    """Отправка AJAX запроса на участие"""
    ajax_url = f"{BASE_URL}/ajax.php"
    payload = {
        "xsrf_token": xsrf_token,
        "code": code
    }
    
    try:
        response = session.post(ajax_url, data=payload)
        
        # Защита от неожиданных HTML-ответов (например, ошибка 502 или Cloudflare)
        if 'application/json' not in response.headers.get('Content-Type', ''):
            logging.warning(f"[!] Сервер вернул не JSON для {code}. Возможно, временный сбой.")
            return xsrf_token

        result = response.json()
        
        if result.get("type") == "success":
            logging.info(f"[+] Успешно вступили в раздачу: {code}")
            # Обновляем токен, если сервер его перевыпустил
            new_xsrf = response.cookies.get("xsrf_token")
            return new_xsrf or xsrf_token
        else:
            msg = result.get("msg", "Неизвестная ошибка")
            logging.warning(f"[-] Ошибка для {code}: {msg}")
            
    except requests.exceptions.JSONDecodeError:
        logging.error(f"[!] Ошибка декодирования JSON для {code}. Ответ: {response.text[:100]}...")
    except Exception as e:
        logging.error(f"[!] Исключение при вступлении в {code}: {e}")
        
    return xsrf_token

def main():
    if not PHPSESSID:
        logging.error("Переменная окружения PHPSESSID не найдена!")
        return

    logging.info("Инициализация сессии...")
    session = init_session()
    
    logging.info("Получение CSRF токена...")
    xsrf_token = get_xsrf_token(session)
    if not xsrf_token:
        return

    logging.info(f"Парсинг раздач со страницы: {TARGET_PAGE_URL}")
    codes = extract_giveaways(session, TARGET_PAGE_URL)
    logging.info(f"Найдено новых раздач для участия: {len(codes)}")

    for i, code in enumerate(codes):
        # Случайная задержка от 3 до 6 секунд (имитация человека)
        sleep_time = random.uniform(3.0, 6.0)
        logging.info(f"Ожидание {sleep_time:.1f} сек перед следующим действием...")
        time.sleep(sleep_time) 
        
        logging.info(f"Попытка вступления ({i+1}/{len(codes)}): {code}")
        xsrf_token = join_giveaway(session, xsrf_token, code)

    logging.info("Готово!")

if __name__ == "__main__":
    main()
