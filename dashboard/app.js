
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

/* Display the latest exchange rates */

async function loadExchangeRates() {
  const sources = ["monex", "bccr", "promerica"];

  try {
    const response = await fetch("rates.json", {
      cache: "no-store"
    });

    if (!response.ok) {
      throw new Error("Unable to load rates");
    }

    const data = await response.json();

    for (const source of sources) {
      const rateElement = document.getElementById(`${source}-rate`);
      const dateElement = document.getElementById(`${source}-date`);
      const observation = data.sources?.[source];

      if (!rateElement || !dateElement) continue;

      if (!observation || !Number.isFinite(observation.rate)) {
        rateElement.textContent = "Rate unavailable";
        dateElement.textContent = "";
        continue;
      }

      rateElement.textContent =
        `₡${observation.rate.toFixed(2)}`;

      if (observation.effective_date) {
        dateElement.textContent =
          `Effective date: ${observation.effective_date}`;
      } else {
        const retrieved = new Date(observation.retrieved_at);

        dateElement.textContent = Number.isNaN(retrieved.getTime())
          ? "Retrieval date unavailable"
          : `Retrieved: ${retrieved.toLocaleString("en-CR", {
              timeZone: "America/Costa_Rica"
            })}`;
      }
    }
  } catch (error) {
    console.error("Exchange-rate loading failed:", error);

    for (const source of sources) {
      const rateElement = document.getElementById(`${source}-rate`);

      if (rateElement) {
        rateElement.textContent = "Rate unavailable";
      }
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
