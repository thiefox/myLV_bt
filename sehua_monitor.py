import time
import hashlib
import requests

def get_homepage_content(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching the homepage: {e}")
        return None

def hash_content(content):
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def main():
    url = "https://www.sehuatang.net/"
    previous_hash = None

    while True:
        content = get_homepage_content(url)
        if content:
            current_hash = hash_content(content)
            if previous_hash and current_hash != previous_hash:
                print("重要：首页发生改变!")
            else :
                print("首页未改变")
            previous_hash = current_hash
        else:
            print("Failed to retrieve the homepage content.")
        
        time.sleep(60)  # Sleep for 1 hour

'''
if __name__ == "__main__":
    main()
'''