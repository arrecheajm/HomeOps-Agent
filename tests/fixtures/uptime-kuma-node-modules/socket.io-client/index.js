"use strict";

function io() {
    const listeners = new Map();
    let nextMonitorID = 10;
    let savedStatusPage = false;

    function reply(args, response) {
        const callback = args.at(-1);
        callback(null, response);
    }

    function fire(event, value) {
        const listener = listeners.get(event);
        if (!listener) {
            throw new Error(`No bootstrap listener registered for ${event}`);
        }
        listeners.delete(event);
        listener(value);
    }

    const socket = {
        once(event, listener) {
            listeners.set(event, listener);
            if (event === "connect") {
                setImmediate(() => fire("connect"));
            }
        },
        timeout() {
            return socket;
        },
        emit(event, ...args) {
            if (event === "needSetup") {
                reply(args, false);
            } else if (event === "login") {
                setImmediate(() => {
                    fire("monitorList", {
                        1: {
                            id: 1,
                            name: "Homepage",
                            type: "http",
                            url: "http://homepage:3000",
                        },
                    });
                    fire("statusPageList", {
                        7: { id: 7, slug: "homeops", title: "HomeOps Status" },
                    });
                    fire("notificationList", []);
                    reply(args, { ok: true });
                });
            } else if (event === "addNotification") {
                const [notification, notificationID] = args;
                if (
                    notificationID !== null ||
                    notification.type !== "ntfy" ||
                    notification.ntfytopic !== "homeops-alerts" ||
                    !notification.ntfyaccesstoken.startsWith("tk_")
                ) {
                    reply(args, { ok: false, msg: "invalid ntfy provider" });
                } else {
                    reply(args, { ok: true, id: 5 });
                }
            } else if (event === "getMonitor") {
                reply(args, {
                    ok: true,
                    monitor: {
                        id: 1,
                        name: "Homepage",
                        type: "http",
                        url: "http://homepage:3000",
                        notificationIDList: {},
                    },
                });
            } else if (event === "editMonitor") {
                const [monitor] = args;
                reply(
                    args,
                    monitor.notificationIDList[5]
                        ? { ok: true, monitorID: monitor.id }
                        : { ok: false, msg: "notification not attached" },
                );
            } else if (event === "add") {
                const [monitor] = args;
                reply(
                    args,
                    monitor.notificationIDList[5]
                        ? { ok: true, monitorID: nextMonitorID++ }
                        : { ok: false, msg: "new monitor has no notification" },
                );
            } else if (event === "getStatusPage") {
                reply(args, { ok: true, config: { id: 7, slug: "homeops" } });
            } else if (event === "addStatusPage") {
                reply(args, { ok: false, msg: "object status page was not found" });
            } else if (event === "saveStatusPage") {
                const groups = args[3];
                const monitorIDs = groups[0].monitorList.map(({ id }) => id);
                savedStatusPage = monitorIDs.length === 4 && monitorIDs.includes(1);
                reply(
                    args,
                    savedStatusPage
                        ? { ok: true }
                        : { ok: false, msg: "status page monitor set is incomplete" },
                );
            } else {
                reply(args, { ok: false, msg: `unexpected event ${event}` });
            }
        },
        disconnect() {
            if (!savedStatusPage) {
                process.exitCode = 9;
            }
        },
    };
    return socket;
}

module.exports = { io };
