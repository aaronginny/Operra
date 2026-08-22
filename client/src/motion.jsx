import { motion, AnimatePresence } from "framer-motion";

// Shared spring presets — tuned for "native mobile app" feel
export const springSoft = { type: "spring", stiffness: 380, damping: 30, mass: 0.7 };
export const springTap  = { type: "spring", stiffness: 700, damping: 22, mass: 0.6 };

// Page transition: fade + slide up
export const pageVariants = {
  initial: { opacity: 0, y: 10 },
  enter:   { opacity: 1, y: 0, transition: { duration: 0.28, ease: [0.22, 0.61, 0.36, 1] } },
  exit:    { opacity: 0, y: -8, transition: { duration: 0.16, ease: "easeIn" } },
};

// List stagger
export const listContainer = {
  enter: { transition: { staggerChildren: 0.04, delayChildren: 0.02 } },
};
export const listItem = {
  initial: { opacity: 0, y: 14 },
  enter:   { opacity: 1, y: 0, transition: springSoft },
  exit:    { opacity: 0, y: -6, transition: { duration: 0.12 } },
};

// Card hover/tap defaults — apply via whileHover / whileTap on motion.* components
export const tapBounce = { scale: 0.96, transition: springTap };
export const hoverLift = { y: -2, transition: springSoft };

// Convenience wrappers
export function MotionPage({ children, ...rest }) {
  return (
    <motion.div variants={pageVariants} initial="initial" animate="enter" exit="exit" {...rest}>
      {children}
    </motion.div>
  );
}

export function MotionList({ children, className, ...rest }) {
  return (
    <motion.div className={className} variants={listContainer} initial="initial" animate="enter" {...rest}>
      {children}
    </motion.div>
  );
}

export function MotionItem({ children, className, ...rest }) {
  return (
    <motion.div className={className} variants={listItem} {...rest}>
      {children}
    </motion.div>
  );
}

export { motion, AnimatePresence };
