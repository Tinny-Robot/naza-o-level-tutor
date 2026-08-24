import {
  BookOpen,
  ClipboardList,
  GraduationCap,
  Home,
  LineChart,
  MessageSquare,
  Sparkles,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { MessageKey } from "../../i18n/en";

export type NavItem = {
  to: string;
  labelKey: MessageKey;
  icon: LucideIcon;
};

export const NAV_ITEMS: NavItem[] = [
  { to: "/", labelKey: "nav.home", icon: Home },
  { to: "/learn", labelKey: "nav.learn", icon: GraduationCap },
  { to: "/tutor", labelKey: "nav.tutor", icon: MessageSquare },
  { to: "/practice", labelKey: "nav.practice", icon: BookOpen },
  { to: "/exams", labelKey: "nav.exams", icon: ClipboardList },
  { to: "/progress", labelKey: "nav.progress", icon: LineChart },
];

export const BRAND = {
  name: "Naza",
  mark: "N",
  taglineKey: "brand.tagline" as MessageKey,
  sparkle: Sparkles,
};
