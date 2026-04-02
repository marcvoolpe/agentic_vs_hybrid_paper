from datetime import datetime

FORMAT = "%Y-%m-%d %H:%M:%S"


def now_datetime() -> str:
    return datetime.now().strftime(FORMAT)


def get_start_time(player: 'Player') -> datetime:
    return datetime.strptime(player.time_start, FORMAT)


def log_debug(*messages: object | tuple[object, ...]):
    message = ' '.join([str(m) for m in messages])
    with open('experiment/static/experiment/debug/debug.log', 'a') as f:
        f.write(f"[{now_datetime()}] {message}\n")


def log_interpret(message: str, llm_output: str, price: float, quantity: float):
    llm_output = llm_output.replace('\n\n', '\n')
    while llm_output.endswith('\n'):
        llm_output = llm_output[:-1]
    file_name = "experiment/static/experiment/debug/interpret.csv"
    with open(file_name, "a") as f:
        f.write(f"MESSAGE {message}\n"
                f"CLEANED {llm_output.replace("\n", "\n        ")}\n"
                f"P / Q   {price} {quantity}\n\n")


def log_function(__clazz__: object | None, method: str | None):
    file_name = "experiment/static/experiment/debug/functions.log"
    module = __clazz__.__module__
    clazz = __clazz__.__name__
    with open(file_name, "a") as f:
        f.write(f"[FUNC] {module:30} {clazz:30} {method:30}\n")


def log_empty():
    file_names = ["experiment/static/experiment/debug/debug.log",
                  "experiment/static/experiment/debug/interpret.csv",
                  "experiment/static/experiment/debug/functions.log"]
    for file_name in file_names:
        with open(file_name, "a") as f:
            f.write("\n\n\n")
