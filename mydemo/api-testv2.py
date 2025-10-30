from zai import ZhipuAiClient

client = ZhipuAiClient(api_key="75ff4962a3e240179b775e1d06186ebd.paqVQs5Tvku5AxK1")  # 填写您自己的APIKey
response = client.chat.completions.create(
    model="glm-4.5v",  # 填写需要调用的模型名称
    messages=[
        {
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://cloudcovert-1305175928.cos.ap-guangzhou.myqcloud.com/%E5%9B%BE%E7%89%87grounding.PNG"
                    }
                },
                {
                    "type": "text",
                    "text": "Where is the second bottle of beer from the right on the table?  Provide coordinates in [[xmin,ymin,xmax,ymax]] format"
                }
            ],
            "role": "user"
        }
    ],
    thinking={
        "type":"enabled"
    },
    stream=True
)

for chunk in response:
    if chunk.choices[0].delta.reasoning_content:
        print(chunk.choices[0].delta.reasoning_content, end='', flush=True)

    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end='', flush=True)