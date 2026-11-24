def normalize(text):
    intervals = []
    for expression in text.split(';'):
        numbers = list(map(int, expression.split('-')))
        intervals.append((numbers[0], numbers[-1]+1))
    return merge(intervals)


def merge(intervals):
    merged = []
    for start, end in sorted((list(span) for span in intervals), key=lambda span: span[0]):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    return merged


def pages_in(spans):
    return sum(end-start for start, end in spans)


def split_limit(intervals, first, last, allowance):
    allowed, out_of_range, exhausted = [], [], []
    for start, end in intervals:
        low, high = max(first, start), min(last+1, end)
        if low >= high:
            out_of_range.append([start, end])
            continue
        if start < low:
            out_of_range.append([start, low])
        if high < end:
            out_of_range.append([high, end])
        taken = min(allowance, high-low)
        if taken:
            allowed.append([low, low+taken])
        if low+taken < high:
            exhausted.append([low+taken, high])
        allowance -= taken
    return allowed, out_of_range, exhausted


def clip(intervals, first, last):
    """裁到刊物页界，返回 (界内段, 越界段)。"""
    inside, outside = [], []
    for start, end in intervals:
        low, high = max(first, start), min(last+1, end)
        if start < low:
            outside.append([start, low])
        if low < high:
            inside.append([low, high])
        if high < end:
            outside.append([high, end])
    return inside, outside


def subtract(intervals, covered):
    """从 intervals 中扣除 covered 已覆盖的部分，剩余段保持升序。"""
    remainder = []
    for start, end in intervals:
        cursor = start
        for cover_start, cover_end in covered:
            if cover_end <= cursor:
                continue
            if cover_start >= end:
                break
            if cover_start > cursor:
                remainder.append([cursor, min(cover_start, end)])
            cursor = max(cursor, cover_end)
            if cursor >= end:
                break
        if cursor < end:
            remainder.append([cursor, end])
    return remainder


def union(*parts):
    return merge([span for part in parts for span in part])


def intersect(left, right):
    overlap = []
    for a_start, a_end in left:
        for b_start, b_end in right:
            low, high = max(a_start, b_start), min(a_end, b_end)
            if low < high:
                overlap.append([low, high])
    return merge(overlap)
