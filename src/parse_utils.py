def strip_comments_and_whitespace(line: str) -> str:
    while True:
        comment_start = line.find("/*")
        comment_end = line.find("*/")
        if comment_start == -1 or comment_end == -1:
            break
        line = line[:comment_start] + line[comment_end + 2 :]
    return line.strip()
