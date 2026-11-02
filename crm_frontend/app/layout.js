// import "./globals.css";
// import { ConnectionProvider } from "@/components/ConnectionContext";
// import Navbar from "@/components/Navbar";

// export const metadata = {
//   title: "ClientCortex",
//   description: "Ask questions about your CRM data",
// };

// export default function RootLayout({ children }) {
//   return (
//     <html lang="en">
//       <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
//         <ConnectionProvider>
//           <Navbar />
//           <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
//         </ConnectionProvider>
//       </body>
//     </html>
//   );
// }

import "./globals.css";
import { ConnectionProvider } from "@/components/ConnectionContext";
import Navbar from "@/components/Navbar";

export const metadata = {
  title: "ClientCortex",
  description: "Ask questions about your CRM data",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body
        suppressHydrationWarning
        className="min-h-screen bg-slate-50 text-slate-900 antialiased"
      >
        <ConnectionProvider>
          <Navbar />
          <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
        </ConnectionProvider>
      </body>
    </html>
  );
}
