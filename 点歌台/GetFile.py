import os
import requests
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

def fetch_github_api(api_url):
    try:
        response = requests.get(api_url, verify=False)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to fetch files. Status code: {response.status_code}")
            return None
    except Exception as e:
        print(f"An error occurred while fetching files: {e}")
        return None

def get_github_repo_files(repo_url):
    api_url = f"https://api.github.com/repos/{repo_url}/contents"
    files = fetch_github_api(api_url)
    message = fetch_message_content(repo_url)
    if files:
        file_names = []
        for file in files:
            if file.get('type') == 'file':
                name = file['name']
                main_name, ext = os.path.splitext(name)
                if main_name.lower() == 'message': 
                #SM的玩意，message.json就是过滤不掉，还是改下点歌台那里吧...
                    continue
                if ext.lower() in ('.mid', '.midi'):
                    file_names.append(main_name)
        return file_names, message
    else:
        return [], message

def fetch_message_content(repo_url):
    """
    获取 Message.json 文件的内容并返回
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0'
        }
        #经过测试，ghproxy.net 似乎是唯一一个能直接下载的,而官方提供的github.tooldelta.top却选择了拒绝连接
        message_url = f"https://ghproxy.net/https://raw.githubusercontent.com/{repo_url}/main/Message.json"
        message_response = requests.get(message_url, headers=headers, verify=False)
        if message_response.status_code == 200:
            return message_response.json().get('message')
        return None
    except Exception as e:
        print(f"Error fetching message: {e}")
        return None