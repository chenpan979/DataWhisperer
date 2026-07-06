import re


# These keywords must never be executed by the Text-to-SQL runtime.
# Prompt rules are useful, but the service-side validator is the real safety boundary.
FORBIDDEN_SQL_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|replace|grant|revoke|call|execute|"
    r"merge|load|outfile|dumpfile)\b",
    re.IGNORECASE,
)


def extract_sql(text: str) -> str:
    """从模型输出中提取 SQL。

    模型有时会返回 ```sql ... ``` 代码块，这里统一提取代码块内部内容。
    """

    value = text.strip()
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", value, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        value = fenced.group(1).strip()
    return value


def validate_select_sql(sql: str) -> str:
    """校验 SQL 是否是单条只读查询。

    在 Text-to-SQL 系统里，模型输出必须当作不可信输入处理：
    模型可能犯错，用户也可能通过 prompt injection 诱导模型生成危险 SQL。
    因此执行前必须在服务端做硬校验。
    """

    cleaned = extract_sql(sql).strip()
    if not cleaned:
        raise ValueError("Generated SQL is empty.")

    cleaned = cleaned.rstrip(";").strip()
    if ";" in cleaned:
        raise ValueError("Only one SQL statement is allowed.")
    if re.search(r"(--|/\*|\*/|#)", cleaned):
        raise ValueError("SQL comments are not allowed.")
    if not re.match(r"^\s*(select|with)\b", cleaned, flags=re.IGNORECASE):
        raise ValueError("Only SELECT queries are allowed.")
    if FORBIDDEN_SQL_RE.search(cleaned):
        raise ValueError("Unsafe SQL keyword detected.")
    return cleaned


def ensure_limit(sql: str, max_rows: int, *, auto_limit_enabled: bool = True) -> str:
    """??????????????????????"""

    cleaned = validate_select_sql(sql)
    limit_match = re.search(r"\blimit\s+(\d+)\s*$", cleaned, flags=re.IGNORECASE)
    if limit_match:
        requested_limit = int(limit_match.group(1))
        if requested_limit <= max_rows:
            return cleaned
        return f"{cleaned[:limit_match.start()].rstrip()}\nLIMIT {max_rows}"
    if not auto_limit_enabled:
        return cleaned
    return f"{cleaned}\nLIMIT {max_rows}"
