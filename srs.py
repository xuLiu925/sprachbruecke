"""FSRS-5 复习算法(纯计算, 不碰数据库)

公式和默认参数与开源的 py-fsrs 5.x (open-spaced-repetition) 一致。
思路: 每个词有「稳定性 S」(天) 和「难度 D」; 在预计还有 90% 把握记得的时候安排复习。
评分: 1 忘了 / 2 困难 / 3 良好 / 4 简单
"""
import math

W = (0.40255, 1.18385, 3.173, 15.69105, 7.1949, 0.5345, 1.4604, 0.0046, 1.54575, 0.1192,
     1.01925, 1.9395, 0.11, 0.29605, 2.2698, 0.2315, 2.9898, 0.51655, 0.6621)
DECAY = -0.5
FACTOR = 0.9 ** (1 / DECAY) - 1
RETENTION = 0.9           # 目标: 复习时还记得的概率
MAX_INTERVAL = 365 * 3    # 最长间隔(天)


def clamp_d(d):
    return min(max(d, 1.0), 10.0)


def init_stability(r):
    return max(W[r - 1], 0.1)


def init_difficulty(r):
    return clamp_d(W[4] - math.exp(W[5] * (r - 1)) + 1)


def retrievability(elapsed_days, s):
    return (1 + FACTOR * elapsed_days / s) ** DECAY


def next_difficulty(d, r):
    delta = -W[6] * (r - 3)
    d2 = d + (10.0 - d) * delta / 9.0
    return clamp_d(W[7] * init_difficulty(4) + (1 - W[7]) * d2)


def recall_stability(d, s, rr, r):
    hard = W[15] if r == 2 else 1
    easy = W[16] if r == 4 else 1
    return s * (1 + math.exp(W[8]) * (11 - d) * s ** -W[9]
                * (math.exp((1 - rr) * W[10]) - 1) * hard * easy)


def forget_stability(d, s, rr):
    long_term = W[11] * d ** -W[12] * ((s + 1) ** W[13] - 1) * math.exp((1 - rr) * W[14])
    return min(long_term, s / math.exp(W[17] * W[18]))


def short_term_stability(s, r):
    return s * math.exp(W[17] * (r - 3 + W[18]))


def next_interval(s):
    days = round(s / FACTOR * (RETENTION ** (1 / DECAY) - 1))
    return min(max(days, 1), MAX_INTERVAL)


def fsrs_review(s, d, last, rating, now):
    """s/d/last 为 None 表示新词。返回 (新稳定性, 新难度, 间隔天数); 忘了 → 间隔 0, 马上再复习"""
    if s is None:
        s, d = init_stability(rating), init_difficulty(rating)
    else:
        elapsed = (now - last).days
        if elapsed < 1:  # 同一天内再次复习
            s = short_term_stability(s, rating)
        else:
            rr = retrievability(elapsed, s)
            s = recall_stability(d, s, rr, rating) if rating > 1 else forget_stability(d, s, rr)
        d = next_difficulty(d, rating)
    return s, d, (0 if rating == 1 else next_interval(s))
