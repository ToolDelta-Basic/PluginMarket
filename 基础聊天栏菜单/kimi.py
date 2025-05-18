import http.client
import json

def askai(text):
    # ------------------------------------------------
    api_key = 1234567890  # 请替换成你的Kimi API Key,可以去https://platform.moonshot.cn/docs/guide/start-using-kimi-api获取
    # ------------------------------------------------
    conn = http.client.HTTPSConnection("api.moonshot.cn")
    payload = json.dumps({
        "model": "moonshot-v1-8k",
        "messages": [
            {"role": "system", "content": f"你是一个回答问题的大师，你更擅长中文和英文的对话。你会为用户提供安全，有帮助，准确的回答。同时，你会拒绝一切涉及恐怖主义，种族歧视，黄色暴力等问题的回答，并且不会有相关词汇出现。并且回答的句子每次不超过5句，而且十分简洁，不会使用markdown格式，换行会在行末添加\n"},
            {"role": "user", "content": f"请简要回答我，5句话以内：{text}"}
        ],
        "temperature": 0.3
    })
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }
    conn.request("POST", "/v1/chat/completions", payload, headers)
    res = conn.getresponse()
    data = res.read()
    completion = json.loads(data.decode("utf-8"))
    ans = completion['choices'][0]['message']
    return ans['content']

