import { useReducedMotion, type Variants } from "framer-motion";

export const pageVariants: Variants = {
  initial: { opacity: 0, y: 12 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] },
  },
  exit: { opacity: 0, y: -8, transition: { duration: 0.2 } },
};

export const reducedPageVariants: Variants = {
  initial: { opacity: 1 },
  animate: { opacity: 1 },
  exit: { opacity: 1 },
};

export const staggerContainer: Variants = {
  animate: { transition: { staggerChildren: 0.06 } },
};

export const reducedStaggerContainer: Variants = {
  animate: { transition: { staggerChildren: 0 } },
};

export const staggerItem: Variants = {
  initial: { opacity: 0, y: 14 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] },
  },
};

export const reducedStaggerItem: Variants = {
  initial: { opacity: 1 },
  animate: { opacity: 1 },
};

export const hoverLift = {
  whileHover: { y: -3, transition: { duration: 0.2 } },
  whileTap: { scale: 0.98 },
};

export function useMotionVariants() {
  const reduce = Boolean(useReducedMotion());
  return {
    reduce,
    page: reduce ? reducedPageVariants : pageVariants,
    container: reduce ? reducedStaggerContainer : staggerContainer,
    item: reduce ? reducedStaggerItem : staggerItem,
    hover: reduce ? {} : hoverLift,
  };
}
