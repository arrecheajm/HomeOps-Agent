"use strict";

// This helper is intentionally coupled to Uptime Kuma 2.4.0's Socket.IO API.
// The deploy action runs it inside the pinned container and passes the admin
// password only through stdin.
const fs = require("node:fs");
const { io } = require("socket.io-client");

const ADMIN_USER = "admin";
const STATUS_PAGE_SLUG = "homeops";
const TIMEOUT_MS = 20_000;
const password = fs.readFileSync(0, "utf8").trim();

if (password.length < 20) {
    throw new Error("Uptime Kuma bootstrap password is missing or too short");
}

const desiredMonitors = [
    { name: "Homepage", url: "http://homepage:3000" },
    { name: "Grafana", url: "http://192.168.86.58:3000/api/health" },
    { name: "Uptime Kuma", url: "http://127.0.0.1:3001" },
    { name: "ntfy", url: "http://ntfy:8080/v1/health" },
];

const socket = io("http://127.0.0.1:3001", {
    transports: ["websocket"],
    timeout: TIMEOUT_MS,
    reconnection: false,
    extraHeaders: { Origin: "http://127.0.0.1:3001" },
});

function waitFor(event) {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(
            () => reject(new Error(`Timed out waiting for ${event}`)),
            TIMEOUT_MS,
        );
        socket.once(event, (value) => {
            clearTimeout(timer);
            resolve(value);
        });
    });
}

function emitAck(event, ...args) {
    return new Promise((resolve, reject) => {
        socket.timeout(TIMEOUT_MS).emit(event, ...args, (error, response) => {
            if (error) {
                reject(new Error(`${event} timed out`));
            } else if (response && response.ok === false) {
                reject(new Error(`${event} failed: ${response.msg || "unknown error"}`));
            } else {
                resolve(response);
            }
        });
    });
}

function monitorPayload(spec) {
    return {
        name: spec.name,
        description: "Provisioned by HomeOps",
        type: "http",
        url: spec.url,
        method: "GET",
        active: true,
        interval: 60,
        retryInterval: 60,
        resendInterval: 0,
        timeout: 10,
        maxretries: 2,
        maxredirects: 10,
        ignoreTls: false,
        upsideDown: false,
        expiryNotification: false,
        accepted_statuscodes: ["200-299"],
        notificationIDList: {},
        kafkaProducerBrokers: [],
        kafkaProducerSaslOptions: {},
        rabbitmqNodes: [],
        conditions: [],
    };
}

async function main() {
    await waitFor("connect");

    const needsSetup = await emitAck("needSetup");
    if (needsSetup) {
        await emitAck("setup", ADMIN_USER, password);
    }

    const initialMonitorList = waitFor("monitorList");
    const initialStatusPageList = waitFor("statusPageList");
    await emitAck("login", { username: ADMIN_USER, password, token: "" });

    const monitorList = await initialMonitorList;
    const monitorByName = new Map(
        Object.values(monitorList || {}).map((monitor) => [monitor.name, monitor]),
    );

    const managedMonitors = [];
    for (const spec of desiredMonitors) {
        const existing = monitorByName.get(spec.name);
        if (existing) {
            if (existing.type !== "http" || existing.url !== spec.url) {
                throw new Error(`Existing monitor ${spec.name} does not match HomeOps`);
            }
            managedMonitors.push({ id: existing.id });
            continue;
        }
        const result = await emitAck("add", monitorPayload(spec));
        managedMonitors.push({ id: result.monitorID });
    }

    const statusPages = await initialStatusPageList;
    const existingPage = (statusPages || []).find(
        (page) => page.slug === STATUS_PAGE_SLUG,
    );
    if (!existingPage) {
        await emitAck("addStatusPage", "HomeOps Status", STATUS_PAGE_SLUG);
    }

    const page = await emitAck("getStatusPage", STATUS_PAGE_SLUG);
    const pageConfig = {
        ...page.config,
        slug: STATUS_PAGE_SLUG,
        title: "HomeOps Status",
        description: "LAN-only status for core HomeOps services.",
        autoRefreshInterval: 60,
        theme: "auto",
        showTags: false,
        footerText: "Managed by HomeOps-Agent",
        customCSS: "",
        showPoweredBy: true,
        showOnlyLastHeartbeat: false,
        showCertificateExpiry: false,
        analyticsId: "",
        analyticsScriptUrl: "",
        analyticsType: null,
        domainNameList: [],
    };
    await emitAck(
        "saveStatusPage",
        STATUS_PAGE_SLUG,
        pageConfig,
        pageConfig.logo || "",
        [{ name: "HomeOps Services", monitorList: managedMonitors }],
    );

    console.log("uptime_kuma_bootstrap_verified");
    socket.disconnect();
}

main().catch((error) => {
    console.error(error.message);
    socket.disconnect();
    process.exitCode = 1;
});
