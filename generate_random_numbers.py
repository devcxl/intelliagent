import random

def generate_random_number(min_val=1, max_val=100):
    """生成一个指定范围内的随机整数"""
    return random.randint(min_val, max_val)

if __name__ == "__main__":
    # 示例：生成1到100之间的随机数
    print("Random number between 1 and 100:", generate_random_number())