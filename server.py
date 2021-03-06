import json

from functools import wraps
from traceback import format_tb
from sys import exc_info
from wsgiref.simple_server import make_server
from wsgiref.util import shift_path_info

from projector import Button, InputSource, RS40, ProjectorCommunicationError

projector = None


class WebException(Exception):
    def __init__(self, code, msg=None):
        self.code = code
        default_msgs = {
            "404 Not Found": "The requested resource could not be found.",
            "503 Service Unavailable": "The underlying service is not available.",
            "500 Internal Server Error": "An internal exception occurred.",
        }

        if not msg:
            if code in default_msgs:
                self.msg = default_msgs[code]
            else:
                self.msg = ""
        else:
            self.msg = msg

    def __repr__(self):
        if not self.msg:
            return self.code
        return "%s: %s" % (self.code, self.msg)

    def __str__(self):
        return "<h1>%s</h1><p>%s</p>" % (self.code, self.msg)


def projector_command(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ProjectorCommunicationError:
            raise WebException(
                "503 Service Unavailable",
                "Could not "
                'communicate with projector "%s". Is it connected and '
                "powered on?" % projector.url,
            )

    return decorated


# information only (this may change if we
# implement an auto-instanciated projector class)
def view_buttons():
    return json.dumps({"names": projector.valid_buttons})


def view_inputs():
    sources = {k: v for k, v in sorted(projector.valid_sources.items(), key=lambda x: x[1])}
    return json.dumps(sources)


@projector_command
def press(button):
    button = button.lower()
    if button not in Button.CODES:
        raise WebException("404 Not Found", "No such button " + button)

    return json.dumps({"success": projector.press_button(button)})


@projector_command
def projector_status():
    return json.dumps(
        {"mode": projector.mode, "input": projector.input, "model": projector.model}
    )


@projector_command
def set_input(source):
    # source = source.lower()
    if source not in projector.valid_sources:
        raise WebException("404 Not Found", "Invalid source " + source)

    return json.dumps({"success": projector.set_input(source)})


@projector_command
def on():
    return json.dumps({"success": projector.turn_on()})


@projector_command
def off():
    return json.dumps({"success": projector.turn_off()})


def index():
    return open("index.html", "rt").read()


def remote_webapp(environ, start_response):
    routes = {
        "buttons": view_buttons,
        "inputs": view_inputs,
        "press": lambda: press(shift_path_info(environ)),
        "status": projector_status,
        "input": lambda: set_input(shift_path_info(environ)),
        "on": on,
        "off": off,
        "": index,
    }

    result = None
    base_path = shift_path_info(environ)
    if base_path not in routes:
        status = "404 Not Found"
        headers = [("Content-type", "text/html")]
        result = str(WebException(status))
    else:
        try:
            handler = routes[base_path]
            result = handler()
            status = "200 OK"  # HTTP Status
            if handler == index:
                headers = [("Content-type", "text/html")]
            else:
                headers = [("Content-type", "application/json")]
        except WebException as ex:
            status = ex.code
            headers = [("Content-type", "text/html")]
            result = str(ex)
        except:
            status = "500 Internal Server Error"
            headers = [("Content-type", "text/html")]
            e_type, e_value, tb = exc_info()
            html = (
                "An internal exception occured. The stacktrace was: "
                "</p><pre>%s\n%s</pre><p>"
                % ("".join(format_tb(tb)), "%s: %s" % (e_type.__name__, e_value))
            )
            result = str(WebException(status, html))

    start_response(status, headers)

    result = result.encode("utf8")
    return [result]


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        sys.stderr.write("Usage: %s [serial device]\n" % sys.argv[0])
    else:
        projector = RS40(sys.argv[1], timeout=0.4)
        httpd = make_server("", 8000, remote_webapp)
        print("Serving on port 8000...")

        # Serve until process is killed
        httpd.serve_forever()
