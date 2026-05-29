from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from models import db
from models.settings import LibrarySetting
from utils.helpers import log_activity
from utils.rfid_reader import RfidHardwareService

rfid_bp = Blueprint("rfid", __name__, url_prefix="/rfid")


@rfid_bp.route("/setup")
def rfid_setup():
    status = RfidHardwareService.get_status()
    ports = RfidHardwareService.list_serial_ports()
    settings = {
        "mode": LibrarySetting.get("rfid_mode", "hid"),
        "port": LibrarySetting.get("rfid_serial_port", "/dev/ttyUSB0"),
        "baud": LibrarySetting.get("rfid_baud_rate", "9600"),
        "prefix": LibrarySetting.get("rfid_tag_prefix", ""),
        "suffix": LibrarySetting.get("rfid_tag_suffix", ""),
        "usb_keyword": LibrarySetting.get("rfid_usb_keyword", ""),
    }
    return render_template(
        "rfid/setup.html", status=status, ports=ports, settings=settings
    )


@rfid_bp.route("/setup/save", methods=["POST"])
def save_rfid_setup():
    mode = request.form.get("rfid_mode", "hid")
    if mode not in ("hid", "serial"):
        mode = "hid"
    port = request.form.get("rfid_serial_port", "").strip()
    baud = request.form.get("rfid_baud_rate", "9600").strip()
    prefix = request.form.get("rfid_tag_prefix", "").strip()
    suffix = request.form.get("rfid_tag_suffix", "").strip()
    usb_keyword = request.form.get("rfid_usb_keyword", "").strip()

    for key, val in [
        ("rfid_mode", mode),
        ("rfid_serial_port", port),
        ("rfid_baud_rate", baud),
        ("rfid_tag_prefix", prefix),
        ("rfid_tag_suffix", suffix),
        ("rfid_usb_keyword", usb_keyword),
    ]:
        setting = LibrarySetting.query.filter_by(key=key).first()
        if setting:
            setting.value = val
        else:
            from models import db

            db.session.add(
                LibrarySetting(
                    key=key,
                    value=val,
                    label=key,
                    description="RFID hardware setting",
                )
            )

    from models import db

    db.session.commit()
    RfidHardwareService.stop()
    if mode == "serial":
        ok, msg = RfidHardwareService.start()
        flash(f"Settings saved. {msg}", "success" if ok else "warning")
    else:
        flash(f"RFID mode set to {mode.upper()}.", "success")

    log_activity("UPDATE", "RFID", None, f"RFID mode: {mode}")
    return redirect(url_for("rfid.rfid_setup"))


@rfid_bp.route("/setup/start", methods=["POST"])
def start_reader():
    ok, msg = RfidHardwareService.start()
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("rfid.rfid_setup"))


@rfid_bp.route("/setup/stop", methods=["POST"])
def stop_reader():
    RfidHardwareService.stop()
    flash("RFID serial reader stopped.", "info")
    return redirect(url_for("rfid.rfid_setup"))


@rfid_bp.route("/test")
def rfid_test():
    return render_template("rfid/test.html", status=RfidHardwareService.get_status())


@rfid_bp.route("/api/connection-status")
def connection_status():
    return jsonify(RfidHardwareService.check_connection())


@rfid_bp.route("/api/config")
def api_config():
    status = RfidHardwareService.get_status()
    return jsonify({
        "mode": status["mode"],
        "port": status["port"],
        "baud": status["baud"],
        "running": status["running"],
        "error": status["error"],
    })


@rfid_bp.route("/api/last-scan")
def api_last_scan():
    since = request.args.get("since", 0)
    scan = RfidHardwareService.get_scan_since(since)
    if scan:
        return jsonify({"success": True, **scan})
    return jsonify({"success": False})


@rfid_bp.route("/api/push-scan", methods=["POST"])
def api_push_scan():
    data = request.get_json() or {}
    tag = (data.get("tag") or "").strip()
    if not tag:
        return jsonify({"success": False, "message": "Empty tag"})
    RfidHardwareService.push_scan(tag, source="hid")
    return jsonify({"success": True, "tag": tag})


@rfid_bp.route("/api/test-port", methods=["POST"])
def api_test_port():
    data = request.get_json() or {}
    ok, msg = RfidHardwareService.test_port(
        data.get("port"), int(data.get("baud", 9600))
    )
    return jsonify({"success": ok, "message": msg})


@rfid_bp.route("/api/ports")
def api_ports():
    return jsonify({"ports": RfidHardwareService.list_serial_ports()})
