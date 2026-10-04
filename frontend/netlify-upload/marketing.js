// Presentation only. No network requests, credentials, sessions or stored inputs.
const planDetails = {
  FREE: ["Free", "€0", "2 CTE attive · 4 comparazioni/mese"],
  START: ["Start", "€14,99/mese", "20 CTE attive · 120 comparazioni/mese"],
  TOP: ["Top", "€44,99/mese", "100 CTE attive · 300 comparazioni/mese"],
};
const selected = new URLSearchParams(location.search).get("piano")?.toUpperCase() ?? "FREE";
const plan = planDetails[selected] ?? planDetails.FREE;
const target = document.querySelector("[data-selected-plan]");
if (target) {
  const title = document.createElement("strong");
  title.textContent = `${plan[0]} — ${plan[1]}`;
  target.replaceChildren("Piano selezionato: ", title, document.createElement("br"), plan[2]);
}
