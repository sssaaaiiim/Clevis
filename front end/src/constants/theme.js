export const BACKEND_URL = ""; // Vite proxy: /api -> http://localhost:8000

export const KNOWN_STATUS = ["Idle", "Planning", "Running", "Validating", "Completed", "Failed"];

/**
 * Blue palette (same lightness steps as the previous cream / teal / gold set).
 *   bg / card ........ ice-blue surfaces
 *   navy / deepBlue .. dark panels and primary buttons
 *   royal ............ secondary highlight (was teal)
 *   sky .............. primary accent (was gold)
 */
export const PALETTE = {
  bg: "#EAF1FB",
  card: "#F4F8FE",
  navy: "#14305E",
  deepBlue: "#2B5BA8",
  royal: "#2F7BD6",
  sky: "#5B9BE6",
  skyLight: "#9CC7F5",
  border: "#C9D9F0",
  border2: "#BCD0EC",
  error: "#7C332B",
  errorBg: "#F3DED8",
};

export const STATUS_STYLES = {
  Idle: { cls: "text-[#1B3F7A] border-[#BCD0EC] bg-[#FAFCFF]" },
  Planning: { cls: "text-[#1B3F7A] border-[#5B9BE6] bg-[#EEF4FC]" },
  Running: { cls: "text-[#1F5AA6] border-[#5B9BE6] bg-[#DDEAFB]" },
  Validating: { cls: "text-[#1B3F7A] border-[#5B9BE6] bg-[#EEF4FC]" },
  Completed: { cls: "text-[#1B3F7A] border-[#2F7BD6]/40 bg-[#E1EEFC]" },
  Failed: { cls: "text-[#7C332B] border-[#C97C6E] bg-[#F3DED8]" },
};

export const QUICK_TEMPLATES = [
  {
    title: "Market scan",
    task: "Find the current Bitcoin price and report it with source link.",
    url: "https://coinmarketcap.com",
  },
  {
    title: "Support discovery",
    task: "Find the support/contact email address and return it.",
    url: "https://stripe.com",
  },
  {
    title: "Knowledge capture",
    task: "Find the top article title and URL.",
    url: "https://news.ycombinator.com",
  },
];
