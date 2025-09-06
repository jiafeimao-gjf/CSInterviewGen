import json
import os.path
import ollama

model_global = "gpt-oss:20b"


def ollama_stream(prompt, model):
    for chunk in ollama.generate(model=model, prompt=prompt,
                                 stream=True):
        text = chunk.get("response", "")
        yield text


def generate_interview():
    # 读取文件
    with open("interview.json", "r") as f:
        data = json.loads(f.read())

    # 遍历数据
    for key, value in data['computer_science_interview_questions'].items():
        if not os.path.exists(f"{key}"):
            os.mkdir(f"{key}")
        # 根据key 创建一该文件
        for question in value:
            with open(f"{key}/{question['question']}.md", "w", encoding="utf-8") as f:
                f.write(f"# 问题：{question['question']}\n")
                print(question['question'])
                f.write(f"回答如下：\n")
                # 调用大模型回答
                response = ollama_stream(question[
                                             'question'] + "，请以10年开发经验的高级开发者，回答这个问题，要求有条理，内容丰富，实践与理论结合！",
                                         model_global)
                for chunk in response:
                    print(chunk)
                    f.write(chunk)


def generate_mysql():
    # 读取文件
    with open("mysql.json", "r") as f:
        data = json.loads(f.read())
    '''
      {
    "title": "MySQL架构与工作原理",
    "content": "MySQL架构分为Server层和存储引擎层。Server层包括连接器、查询缓存、解析器/分析器、优化器和执行器。连接器负责客户端连接管理，使用长连接减少创建和释放连接的开销。查询缓存在MySQL 8.0中已被移除，因为SQL语句微小变化就会导致缓存失效。解析器将SQL语句解析为抽象语法树，优化器决定最佳执行计划。存储引擎层负责数据的存储和检索，InnoDB是默认引擎，支持事务和行级锁。",
    "example": "连接器使用长连接管理，例如：druid、c3p0、dbcp等连接池技术"
  },
    '''
    os.mkdir("mysql")
    for item in data:
        with open(f"mysql/{item['title']}.md", "w", encoding="utf-8") as f:
            f.write(f"# 问题：{item['title']}\n")
            f.write(f"回答如下：\n")
            # 构造prompt 让模型进行一步细化输出
            prompt = (f"「{item['title']}」 请根据以下内容：\n{item['content']}\n 示例：\n{item['example']}\n 细化回答: \n "
                      f"要求：1. 回答要详细，内容丰富，实践与理论结合！2. 回答要符合中文语法规范！3、适当进行图示说明")
            f.write(prompt)
            response = ollama_stream(prompt, model_global)
            for chunk in response:
                print(chunk)
                f.write(chunk)


def redis_interview():
    read_json_llm_answer("redis.json", "redis_openai")


def system_design_interview():
    # 读取文件
    read_json_llm_answer("system_design_all.json", "system_design")


def generate_mysql_new():
    read_json_llm_answer("mysql_new.json", "mysql_new")


def read_json_llm_answer(json_file, output_dir):
    with open(json_file, "r") as f:
        data = json.loads(f.read())
        if not os.path.exists(output_dir):
            os.mkdir(output_dir)
        for item in data:
            item["title"] = item['title'].replace("/", "-")
            if os.path.exists(f"{output_dir}/{item['title']}.md"):
                continue
            with open(f"{output_dir}/{item['title']}.md", "w", encoding="utf-8") as f:
                f.write(f"# 问题：{item['title']}\n")
                f.write(f"回答如下：\n")
                # 构造prompt 让模型进行一步细化输出
                prompt = (f"「{item['title']}」 请根据以下内容：\n{item['content']}\n 细化回答: \n "
                          f"要求：1. 回答要详细，内容丰富，实践与理论结合！2. 采用总分总的文章思路！3、适当进行图示说明")
                f.write(prompt)
                response = ollama_stream(prompt, model_global)
                for chunk in response:
                    print(chunk)
                    f.write(chunk)


def chat_by_input():
    print("基于大模型的问答系统")
    while True:
        prompt = input("请输入问题：")
        if prompt == "exit":
            break
        chat_by_prompt(prompt)


def chat_by_prompt(prompt):
    response = ollama_stream(prompt, model_global)
    length = 0
    with open(f"{prompt.replace('/', '-')}.md", "w", encoding="utf-8") as f:
        f.write(f"# 问题：{prompt}\n")
        f.write(f"回答如下：\n")
        for chunk in response:
            # print(chunk)
            length += len(chunk)
            if length % 100 == 0:
                print(f"当前长度：{length}")
            f.write(chunk)


if __name__ == '__main__':
    # generate_mysql_new()
    # prompt = "帮我写一篇关于互联网系统架构演变（基于Java的微服务架构）的文章，要求内容丰富，实践与理论结合，适当进行图示说明"
    # chat_by_prompt(prompt)
    # redis_interview()

    chat_by_input()
