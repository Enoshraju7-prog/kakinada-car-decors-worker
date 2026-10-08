import {
  Boxes,
  PackageCheck,
  ShoppingBag,
  History,
  ClipboardCheck,
  Bot,
  ScanLine,
  PackagePlus,
} from "@/lib/icons";

export const views = {
  stock: [
    "Check inventory",
    "Inventory",
    "Available stock, incoming goods and items that need your attention.",
  ],
  incoming: [
    "Receive stock",
    "Purchases & receiving",
    "Record supplier bills, then count goods when they reach the shop.",
  ],
  sale: [
    "Make sale",
    "Make a sale",
    "Choose the right products, add fitting and review the total.",
  ],
  approvals: [
    "Approvals",
    "Review & approve",
    "Check bill details and physical counts before saving them to stock.",
  ],
  history: [
    "Activity",
    "Shop activity",
    "Review purchases, sales, returns and the stock changes behind them.",
  ],
  worker: [
    "AI assistant",
    "AI assistant",
    "Give it a task. Review its work. Stay in control of what gets saved.",
  ],
  catalogue: [
    "Products",
    "Product catalogue",
    "Add the exact variants you stock, with confirmed units and packaging.",
  ],
  corrections: [
    "Stock corrections",
    "Stock corrections",
    "Record a checked physical count with a reason for the change.",
  ],
} as const;
export type View = keyof typeof views;
export const navigation = [
  { key: "stock", icon: Boxes, group: "Daily work" },
  { key: "incoming", icon: PackageCheck, group: "Daily work" },
  { key: "sale", icon: ShoppingBag, group: "Daily work" },
  { key: "approvals", icon: ClipboardCheck, group: "Daily work" },
  { key: "history", icon: History, group: "Daily work" },
  { key: "worker", icon: Bot, group: "Management" },
  { key: "catalogue", icon: PackagePlus, group: "Management" },
  { key: "corrections", icon: ScanLine, group: "Management" },
] satisfies { key: View; icon: typeof Boxes; group: string }[];
