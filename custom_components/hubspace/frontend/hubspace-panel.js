const CONTROL_SPECS = [
  {
    key: "freezer_target",
    suffix: "_freezer_target_temperature",
    domain: "number",
    section: "controls",
    labelSuffix: " Freezer Target Temperature",
  },
  {
    key: "fridge_target",
    suffix: "_fridge_target_temperature",
    domain: "number",
    section: "controls",
    labelSuffix: " Fridge Target Temperature",
  },
  {
    key: "mode",
    suffix: "_mode",
    domain: "select",
    section: "controls",
    labelSuffix: " Mode",
  },
  {
    key: "temperature_units",
    suffix: "_temperature_units",
    domain: "select",
    section: "controls",
    labelSuffix: " Temperature Units",
  },
  {
    key: "super_cold",
    suffix: "_super_cold",
    domain: "switch",
    section: "controls",
    labelSuffix: " Super Cold",
  },
];

const STATUS_SPECS = [
  {
    key: "freezer_status",
    suffix: "_freezer_super_cold_status",
    domain: "sensor",
    section: "status",
    labelSuffix: " Freezer Super Cold Status",
  },
  {
    key: "refrigerator_status",
    suffix: "_refrigerator_super_cold_status",
    domain: "sensor",
    section: "status",
    labelSuffix: " Refrigerator Super Cold Status",
  },
];

const ALERT_SPECS = [
  {
    key: "freezer_high_temp_alert",
    suffix: "_freezer_high_temp_alert",
    domain: "binary_sensor",
    section: "alerts",
    labelSuffix: " Freezer High Temp Alert",
  },
  {
    key: "fridge_high_temp_alert",
    suffix: "_fridge_high_temp_alert",
    domain: "binary_sensor",
    section: "alerts",
    labelSuffix: " Fridge High Temp Alert",
  },
  {
    key: "sensor_failure",
    suffix: "_sensor_failure",
    domain: "binary_sensor",
    section: "alerts",
    labelSuffix: " Sensor Failure",
  },
  {
    key: "mcu_communication_failure",
    suffix: "_mcu_communication_failure",
    domain: "binary_sensor",
    section: "alerts",
    labelSuffix: " MCU Communication Failure",
  },
];

const ENTITY_SPECS = [...CONTROL_SPECS, ...STATUS_SPECS, ...ALERT_SPECS].sort(
  (left, right) => right.suffix.length - left.suffix.length
);

const FREEZER_MARKER_KEYS = new Set([
  "freezer_target",
  "fridge_target",
  "super_cold",
  "freezer_status",
  "refrigerator_status",
  "freezer_high_temp_alert",
  "fridge_high_temp_alert",
  "sensor_failure",
  "mcu_communication_failure",
]);

const CONTROL_ORDER = [
  "super_cold",
  "freezer_target",
  "fridge_target",
  "mode",
  "temperature_units",
];

const STATUS_ORDER = ["freezer_status", "refrigerator_status"];

const ALERT_ORDER = [
  "freezer_high_temp_alert",
  "fridge_high_temp_alert",
  "sensor_failure",
  "mcu_communication_failure",
];

class HubspaceFreezerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = undefined;
    this._panel = undefined;
    this._route = undefined;
    this._narrow = false;
    this._renderToken = 0;
    this._helpersPromise = undefined;
  }

  set hass(value) {
    this._hass = value;
    this._render();
  }

  set panel(value) {
    this._panel = value;
    this._render();
  }

  set route(value) {
    this._route = value;
    this._render();
  }

  set narrow(value) {
    this._narrow = Boolean(value);
    this._render();
  }

  _allStates() {
    if (!this._hass?.states) {
      return [];
    }
    return Object.entries(this._hass.states).map(([entityId, stateObj]) => ({
      entityId,
      stateObj,
    }));
  }

  _matchSpec(entityId) {
    return ENTITY_SPECS.find((spec) => {
      return entityId.startsWith(`${spec.domain}.`) && entityId.endsWith(spec.suffix);
    });
  }

  _groupId(entityId, suffix) {
    const objectId = entityId.split(".", 2)[1];
    return objectId.slice(0, -suffix.length);
  }

  _humanizeSlug(value) {
    return String(value || "")
      .split("_")
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
  }

  _deriveLabel(groupId, spec, stateObj) {
    const friendlyName = String(stateObj?.attributes?.friendly_name || "").trim();
    if (!friendlyName) {
      return this._humanizeSlug(groupId);
    }
    if (spec?.labelSuffix && friendlyName.endsWith(spec.labelSuffix)) {
      return friendlyName.slice(0, -spec.labelSuffix.length).trim();
    }
    return friendlyName;
  }

  _labelRank(key) {
    const ranks = {
      freezer_target: 0,
      fridge_target: 1,
      super_cold: 2,
      freezer_status: 3,
    };
    return ranks[key] ?? 99;
  }

  _collectFreezerGroups() {
    const groups = new Map();

    for (const { entityId, stateObj } of this._allStates()) {
      const spec = this._matchSpec(entityId);
      if (!spec) {
        continue;
      }

      const groupId = this._groupId(entityId, spec.suffix);
      if (!groups.has(groupId)) {
        groups.set(groupId, {
          groupId,
          label: undefined,
          labelRank: 999,
          controls: new Map(),
          status: new Map(),
          alerts: new Map(),
        });
      }

      const group = groups.get(groupId);
      group[spec.section].set(spec.key, entityId);
      const rank = this._labelRank(spec.key);
      if (group.label === undefined || rank < group.labelRank) {
        group.label = this._deriveLabel(groupId, spec, stateObj);
        group.labelRank = rank;
      }
    }

    return [...groups.values()]
      .filter((group) => {
        const keys = [
          ...group.controls.keys(),
          ...group.status.keys(),
          ...group.alerts.keys(),
        ];
        return keys.some((key) => FREEZER_MARKER_KEYS.has(key));
      })
      .map((group) => ({
        ...group,
        label: group.label || this._humanizeSlug(group.groupId),
      }))
      .sort((left, right) => left.label.localeCompare(right.label));
  }

  _entityId(group, section, key) {
    return group?.[section]?.get(key);
  }

  _stateValue(entityId) {
    return this._hass?.states?.[entityId];
  }

  _stateText(entityId, fallback = "Unavailable") {
    const stateObj = this._stateValue(entityId);
    const value = String(stateObj?.state || "").trim();
    if (!value || value === "unknown" || value === "unavailable") {
      return fallback;
    }
    return value;
  }

  _isOn(entityId) {
    return this._stateText(entityId, "off") === "on";
  }

  _activeAlertEntities(group) {
    return ALERT_ORDER.map((key) => this._entityId(group, "alerts", key))
      .filter(Boolean)
      .filter((entityId) => this._isOn(entityId));
  }

  _overviewCard(groups) {
    const activeAlertEntities = groups.flatMap((group) =>
      this._activeAlertEntities(group)
    );
    const activeSuperCold = groups.filter((group) =>
      this._isOn(this._entityId(group, "controls", "super_cold"))
    ).length;
    const devicesWithAlerts = groups.filter(
      (group) => this._activeAlertEntities(group).length > 0
    ).length;

    const card = document.createElement("ha-card");
    card.innerHTML = `
      <div class="overview-card">
        <div class="card-title">Freezer Overview</div>
        <div class="metric-grid">
          <div class="metric">
            <div class="metric-label">Freezers</div>
            <div class="metric-value">${groups.length}</div>
          </div>
          <div class="metric">
            <div class="metric-label">Super Cold Active</div>
            <div class="metric-value">${activeSuperCold}</div>
          </div>
          <div class="metric">
            <div class="metric-label">Devices With Alerts</div>
            <div class="metric-value">${devicesWithAlerts}</div>
          </div>
          <div class="metric">
            <div class="metric-label">Active Alerts</div>
            <div class="metric-value">${activeAlertEntities.length}</div>
          </div>
        </div>
      </div>
    `;
    return card;
  }

  _summaryCard(group) {
    const mode = this._stateText(this._entityId(group, "controls", "mode"), "unknown");
    const units = this._stateText(
      this._entityId(group, "controls", "temperature_units"),
      "unknown"
    );
    const freezerTarget = this._stateText(
      this._entityId(group, "controls", "freezer_target"),
      "unknown"
    );
    const fridgeTarget = this._stateText(
      this._entityId(group, "controls", "fridge_target"),
      "unknown"
    );
    const superCold = this._isOn(this._entityId(group, "controls", "super_cold"))
      ? "on"
      : "off";
    const activeAlerts = this._activeAlertEntities(group);
    const statusTone =
      activeAlerts.length > 0
        ? "var(--error-color)"
        : superCold === "on"
          ? "var(--warning-color)"
          : "var(--success-color)";
    const statusText =
      activeAlerts.length > 0
        ? `${activeAlerts.length} alert${activeAlerts.length === 1 ? "" : "s"}`
        : superCold === "on"
          ? "super cold active"
          : "normal";

    const card = document.createElement("ha-card");
    card.innerHTML = `
      <div class="summary-card">
        <div class="summary-top">
          <div>
            <div class="card-title">${group.label}</div>
            <div class="device-subtitle">Targets and live freezer status</div>
          </div>
          <div class="status-pill" style="--status-color:${statusTone}">
            ${statusText}
          </div>
        </div>
        <div class="metric-grid compact">
          <div class="metric">
            <div class="metric-label">Mode</div>
            <div class="metric-value small">${mode}</div>
          </div>
          <div class="metric">
            <div class="metric-label">Units</div>
            <div class="metric-value small">${units}</div>
          </div>
          <div class="metric">
            <div class="metric-label">Freezer Target</div>
            <div class="metric-value small">${freezerTarget}</div>
          </div>
          <div class="metric">
            <div class="metric-label">Fridge Target</div>
            <div class="metric-value small">${fridgeTarget}</div>
          </div>
          <div class="metric">
            <div class="metric-label">Super Cold</div>
            <div class="metric-value small">${superCold}</div>
          </div>
        </div>
      </div>
    `;
    return card;
  }

  _emptyCard(message) {
    const card = document.createElement("ha-card");
    const content = document.createElement("div");
    content.className = "empty-card";
    content.textContent = message;
    card.appendChild(content);
    return card;
  }

  async _createCard(config) {
    if (!this._helpersPromise) {
      const loadHelpers = window.loadCardHelpers;
      this._helpersPromise =
        typeof loadHelpers === "function" ? loadHelpers() : Promise.resolve(undefined);
    }
    const helpers = await this._helpersPromise;
    if (helpers?.createCardElement) {
      return helpers.createCardElement(config);
    }
    await customElements.whenDefined("hui-entities-card");
    const card = document.createElement("hui-entities-card");
    if (typeof card.setConfig === "function") {
      card.setConfig(config);
    }
    return card;
  }

  async _entitiesCard(title, entities) {
    if (!entities.length) {
      return this._emptyCard(`No ${title.toLowerCase()} available.`);
    }
    return this._createCard({
      type: "entities",
      title,
      show_header_toggle: false,
      state_color: true,
      entities,
    });
  }

  _sectionEntities(group, section, order) {
    return order
      .map((key) => this._entityId(group, section, key))
      .filter(Boolean);
  }

  async _render() {
    if (!this.shadowRoot) {
      return;
    }

    const token = ++this._renderToken;
    const title = this._panel?.config?.title || "Hubspace Freezers";

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          min-height: 100%;
          background: var(--lovelace-background, var(--primary-background-color));
          color: var(--primary-text-color);
        }
        .page {
          max-width: 1440px;
          margin: 0 auto;
          padding: 24px 16px 40px;
        }
        .hero {
          margin-bottom: 20px;
        }
        .eyebrow {
          color: var(--secondary-text-color);
          font-size: 12px;
          font-weight: 600;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          margin-bottom: 8px;
        }
        h1 {
          margin: 0;
          font-size: 32px;
          line-height: 1.1;
          font-weight: 700;
        }
        .lede {
          margin-top: 10px;
          color: var(--secondary-text-color);
          max-width: 860px;
          line-height: 1.5;
        }
        .section {
          margin-top: 24px;
        }
        .section h2 {
          margin: 0 0 12px;
          font-size: 18px;
          line-height: 1.2;
          font-weight: 600;
        }
        .cards {
          display: grid;
          gap: 16px;
        }
        .cards.columns-3 {
          grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
        }
        .overview-card,
        .summary-card {
          padding: 16px;
        }
        .summary-top {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 12px;
        }
        .card-title {
          font-size: 16px;
          font-weight: 600;
          line-height: 1.2;
        }
        .device-subtitle {
          margin-top: 6px;
          color: var(--secondary-text-color);
          font-size: 13px;
        }
        .metric-grid {
          display: grid;
          gap: 12px;
          margin-top: 14px;
          grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        }
        .metric-grid.compact {
          grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
        }
        .metric {
          padding: 12px;
          border-radius: 12px;
          background: var(--secondary-background-color);
        }
        .metric-label {
          color: var(--secondary-text-color);
          font-size: 12px;
          line-height: 1.3;
          margin-bottom: 6px;
        }
        .metric-value {
          font-size: 26px;
          font-weight: 700;
          line-height: 1.1;
        }
        .metric-value.small {
          font-size: 18px;
        }
        .status-pill {
          padding: 6px 10px;
          border-radius: 999px;
          background: color-mix(in srgb, var(--status-color) 18%, transparent);
          color: var(--status-color);
          font-size: 12px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          white-space: nowrap;
        }
        .empty-card {
          padding: 16px;
          color: var(--secondary-text-color);
        }
        @media (max-width: 720px) {
          .page {
            padding: 16px 12px 32px;
          }
          h1 {
            font-size: 26px;
          }
        }
      </style>
      <div class="page">
        <div class="hero">
          <div class="eyebrow">Hubspace</div>
          <h1>${title}</h1>
          <div class="lede">
            Adjust freezer targets, mode, units, and super-cold from one place.
            This page reuses the existing Hubspace entities, so changes here use
            the same Home Assistant controls and services as the entity pages.
          </div>
        </div>
        <div id="content" class="cards"></div>
      </div>
    `;

    const mount = this.shadowRoot.querySelector("#content");
    if (!this._hass) {
      mount.append(this._emptyCard("Home Assistant state is not available yet."));
      return;
    }

    const groups = this._collectFreezerGroups();
    if (!groups.length) {
      mount.append(
        this._emptyCard(
          "No Hubspace freezer entities were found. Reload the integration after your freezer entities appear."
        )
      );
      return;
    }

    mount.append(this._overviewCard(groups));

    for (const group of groups) {
      if (token !== this._renderToken) {
        return;
      }

      const section = document.createElement("section");
      section.className = "section";
      section.innerHTML = `
        <h2>${group.label}</h2>
        <div class="cards columns-3"></div>
      `;
      mount.append(section);

      const cardsMount = section.querySelector(".cards");
      const cards = [
        this._summaryCard(group),
        await this._entitiesCard(
          `${group.label} Controls`,
          this._sectionEntities(group, "controls", CONTROL_ORDER)
        ),
        await this._entitiesCard(
          `${group.label} Status`,
          this._sectionEntities(group, "status", STATUS_ORDER)
        ),
        await this._entitiesCard(
          `${group.label} Alerts`,
          this._sectionEntities(group, "alerts", ALERT_ORDER)
        ),
      ];

      for (const card of cards) {
        if (token !== this._renderToken) {
          return;
        }
        if (card && typeof card === "object" && "hass" in card) {
          card.hass = this._hass;
        }
        cardsMount.append(card);
      }
    }
  }
}

customElements.define("hubspace-freezer-panel", HubspaceFreezerPanel);
