import { redirect } from "next/navigation";

/** Platform bindings moved to Admin → Acesso, tab Concessões (spec 0018 CA11). */
export default function PlatformAccessPage() {
  redirect("/admin/access");
}
