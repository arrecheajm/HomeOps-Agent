"use strict";

const NOTIFICATION_NAME = "HomeOps ntfy";
const NTFY_TOPIC = "homeops-alerts";

function values(collection) {
    if (!collection || typeof collection !== "object") {
        return [];
    }
    return Array.isArray(collection) ? collection : Object.values(collection);
}

function parseBootstrapInput(text) {
    let input;
    try {
        input = JSON.parse(text);
    } catch (_error) {
        throw new Error("Bootstrap input must be valid JSON");
    }
    const password = input.uptimeKumaAdminPassword;
    const ntfyAccessToken = input.ntfyAccessToken;
    if (typeof password !== "string" || password.length < 20) {
        throw new Error("Uptime Kuma bootstrap password is missing or too short");
    }
    if (typeof ntfyAccessToken !== "string" || !/^tk_[a-z0-9]{29}$/.test(ntfyAccessToken)) {
        throw new Error("ntfy service token is missing or malformed");
    }
    return { password, ntfyAccessToken };
}

function findStatusPage(statusPages, slug) {
    return values(statusPages).find((page) => page.slug === slug);
}

function findNotification(notifications) {
    return values(notifications).find(
        (notification) => notification.name === NOTIFICATION_NAME,
    );
}

function notificationType(notification) {
    if (!notification) {
        return undefined;
    }
    if (typeof notification.type === "string") {
        return notification.type;
    }
    if (typeof notification.config === "object" && notification.config) {
        return notification.config.type;
    }
    if (typeof notification.config === "string") {
        try {
            return JSON.parse(notification.config).type;
        } catch (_error) {
            return undefined;
        }
    }
    return undefined;
}

function ntfyNotificationPayload(ntfyAccessToken) {
    return {
        name: NOTIFICATION_NAME,
        type: "ntfy",
        active: true,
        isDefault: false,
        applyExisting: false,
        ntfyserverurl: "http://ntfy:8080",
        ntfytopic: NTFY_TOPIC,
        ntfyAuthenticationMethod: "accessToken",
        ntfyaccesstoken: ntfyAccessToken,
        ntfyPriority: 4,
        ntfyPriorityDown: 5,
        ntfyCall: "",
        ntfyIcon: "",
        ntfyUseTemplate: false,
        ntfyCustomTitle: "",
        ntfyCustomMessage: "",
    };
}

function withNotification(notificationIDList, notificationID) {
    return {
        ...(notificationIDList || {}),
        [notificationID]: true,
    };
}

module.exports = {
    NTFY_TOPIC,
    findNotification,
    findStatusPage,
    notificationType,
    ntfyNotificationPayload,
    parseBootstrapInput,
    values,
    withNotification,
};
