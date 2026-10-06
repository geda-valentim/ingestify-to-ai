import { Layers } from "lucide-react";
import styles from "./brand.module.css";

/** The same undistorted mark across the public site and application. */
export function Brand() {
  return (
    <span className={styles.brand}>
      <span className={styles.mark} aria-hidden="true">
        <Layers size={20} strokeWidth={1.5} />
      </span>
      <span>ingestify.</span>
    </span>
  );
}
