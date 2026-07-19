import { redirect } from "next/navigation";

// The app has no public landing page; send everyone to the dashboard, which
// bounces to /login when there is no session.
export default function Home() {
  redirect("/dashboard");
}
