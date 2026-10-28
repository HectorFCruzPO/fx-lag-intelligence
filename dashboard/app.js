
document.addEventListener("DOMContentLoaded", () => {
  const loader = document.getElementById("brand-loader");
  const typedBrand = document.getElementById("typed-brand");

  if (!loader || !typedBrand) return;

  const brandName = "Development";
  const typingStart = 3300;
  const typingSpeed = 110;

  // Type "Development" one letter at a time.
  brandName.split("").forEach((letter, index) => {
    setTimeout(() => {
      typedBrand.textContent += letter;
    }, typingStart + index * typingSpeed);
  });

  // Reveal the dashboard after the animation.
  const animationEnd =
    typingStart + brandName.length * typingSpeed + 700;

  setTimeout(() => {
    loader.classList.add("fade-out");

    setTimeout(() => {
      loader.remove();
    }, 700);
  }, animationEnd);
});


/* Display latest rates, changes, and data freshness */

function formatCostaRicaTime(timestamp) {
  if (!timestamp) return "Unavailable";

  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime())) {
    return "Unavailable";
  }

  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Costa_Rica",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true
  }).format(date);
}

function displayRateChange(source, observations) {
  const element = document.getElementById(`${source}-change`);
  if (!element) return;

  const valid = (observations || [])
    .filter(item =>
      Number.isFinite(item.rate) &&
      Number.isFinite(Date.parse(item.retrieved_at))
    )
    .sort((a, b) =>
      Date.parse(a.retrieved_at) - Date.parse(b.retrieved_at)
    );

  // MONEX and BCCR: compare consecutive effective dates.
  // Promerica: compare the latest rate with the previous
  // different collected rate.
  let current;
  let previous;

  if (source === "promerica") {
    current = valid.at(-1);
    previous = valid.slice(0, -1)
      .reverse()
      .find(item => item.rate !== current?.rate);
  } else {
    const byDate = new Map();

    for (const item of valid) {
      if (item.effective_date) {
        byDate.set(item.effective_date, item);
      }
    }

    const ordered = [...byDate.values()]
      .sort((a, b) =>
        a.effective_date.localeCompare(b.effective_date)
      );

    current = ordered.at(-1);
    previous = ordered.at(-2);
  }

  element.classList.remove("rate-up", "rate-down", "rate-flat");

  if (!current || !previous) {
    element.textContent = "Change unavailable";
    element.classList.add("rate-flat");
    return;
  }

  const change = current.rate - previous.rate;
  const amount = Math.abs(change).toFixed(2);

  if (Math.abs(change) < 0.005) {
    element.textContent = "→ No change";
    element.classList.add("rate-flat");
  } else if (change > 0) {
    element.textContent = `↑ +₡${amount}`;
    element.classList.add("rate-up");
  } else {
    element.textContent = `↓ -₡${amount}`;
    element.classList.add("rate-down");
  }
}

async function loadExchangeRates() {
  const sources = ["monex", "bccr", "promerica"];
  const updatedElement = document.getElementById("last-updated");

  try {
    const response = await fetch("rates.json", {
      cache: "no-store"
    });

    if (!response.ok) {
      throw new Error("Unable to load rates");
    }

    const data = await response.json();
    const timestamps = [];

    for (const source of sources) {
      const rateElement = document.getElementById(`${source}-rate`);
      const dateElement = document.getElementById(`${source}-date`);
      const observation = data.sources?.[source];

      if (!rateElement || !dateElement) continue;

      if (!observation || !Number.isFinite(observation.rate)) {
        rateElement.textContent = "Rate unavailable";
        dateElement.textContent = "";
        displayRateChange(source, []);
        continue;
      }

      rateElement.textContent = `\u20A1${observation.rate.toFixed(2)}`;

      if (observation.effective_date) {
        dateElement.textContent =
          `Effective date: ${observation.effective_date}`;
      } else {
        dateElement.textContent =
          `Retrieved: ${formatCostaRicaTime(observation.retrieved_at)}`;
      }

      const timestamp = Date.parse(observation.retrieved_at);
      if (Number.isFinite(timestamp)) {
        timestamps.push(timestamp);
      }

      displayRateChange(source, data.history?.[source] || []);
    }

    if (updatedElement) {
      updatedElement.textContent = timestamps.length
        ? `Data last collected: ${formatCostaRicaTime(
            new Date(Math.max(...timestamps)).toISOString()
          )} (Costa Rica)`
        : "Data last collected: Unavailable";
    }

  } catch (error) {
    console.error("Exchange-rate loading failed:", error);

    if (updatedElement) {
      updatedElement.textContent = "Data last collected: Unavailable";
    }

    for (const source of sources) {
      const rateElement = document.getElementById(`${source}-rate`);
      const changeElement = document.getElementById(`${source}-change`);

      if (rateElement) rateElement.textContent = "Rate unavailable";
      if (changeElement) changeElement.textContent = "Change unavailable";
    }
  }
}

document.addEventListener("DOMContentLoaded", loadExchangeRates);

/* Historical exchange-rate chart */

async function loadHistoryChart() {
  const canvas = document.getElementById("history-chart");
  const status = document.getElementById("chart-status");

  if (!canvas || !status) return;

  try {
    if (typeof Chart === "undefined") {
      throw new Error("Chart.js did not load");
    }

    const response = await fetch("rates.json", {
      cache: "no-store"
    });

    if (!response.ok) {
      throw new Error("Could not load historical data");
    }

    const data = await response.json();

    const sources = [
      { key: "monex", label: "MONEX", color: "#d4a853" },
      { key: "bccr", label: "BCCR", color: "#38bdf8" },
      { key: "promerica", label: "Promerica", color: "#4ade80" }
    ];

    // Use actual observation dates; never invent missing rates.
    const dayFor = (source, observation) => {
      const timestamp = source === "promerica"
        ? observation.retrieved_at
        : observation.effective_date;

      if (!timestamp) return null;

      if (source !== "promerica") {
        return timestamp.slice(0, 10);
      }

      const date = new Date(timestamp);
      if (Number.isNaN(date.getTime())) return null;

      // Group Promerica observations by Costa Rica calendar day.
      return new Intl.DateTimeFormat("en-CA", {
        timeZone: "America/Costa_Rica",
        year: "numeric",
        month: "2-digit",
        day: "2-digit"
      }).format(date);
    };

    const daily = {};
    const allDays = new Set();

    for (const source of sources) {
      const observations = data.history?.[source.key] || [];
      const byDay = new Map();

      for (const observation of observations) {
        const day = dayFor(source.key, observation);

        if (!day || !Number.isFinite(observation.rate)) continue;

        const previous = byDay.get(day);

        // Keep the last retrieved observation for each day.
        if (
          !previous ||
          observation.retrieved_at > previous.retrieved_at
        ) {
          byDay.set(day, observation);
        }
      }

      daily[source.key] = byDay;
      for (const day of byDay.keys()) allDays.add(day);
    }

    const days = [...allDays].sort();

    if (days.length === 0) {
      status.textContent = "No historical observations available yet.";
      return;
    }

    const datasets = sources.map(source => ({
      label: source.label,
      data: days.map(day => daily[source.key].get(day)?.rate ?? null),
      borderColor: source.color,
      backgroundColor: source.color,
      borderWidth: 2,
      pointRadius: 4,
      tension: 0.25,
      spanGaps: false
    }));

    new Chart(canvas, {
      type: "line",
      data: {
        labels: days,
        datasets
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: "index",
          intersect: false
        },
        plugins: {
          legend: {
            labels: { color: "#f1f5f9" }
          },
          tooltip: {
            callbacks: {
              label: context => {
                if (context.parsed.y === null) return "";
                return `${context.dataset.label}: ₡${context.parsed.y.toFixed(2)}`;
              }
            }
          }
        },
        scales: {
          x: {
            ticks: { color: "#94a3b8" },
            grid: { color: "#253247" }
          },
          y: {
            ticks: {
              color: "#94a3b8",
              callback: value => `₡${value}`
            },
            grid: { color: "#253247" }
          }
        }
      }
    });

    status.textContent =
      "Historical observations from collected data. " +
      "MONEX and BCCR use effective dates; " +
      "Promerica uses the last retrieved rate per Costa Rica day.";

  } catch (error) {
    console.error("Historical chart error:", error);
    status.textContent = "Historical chart unavailable.";
  }
}

document.addEventListener("DOMContentLoaded", loadHistoryChart);
