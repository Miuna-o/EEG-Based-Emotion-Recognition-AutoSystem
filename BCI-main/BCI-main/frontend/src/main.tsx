import { createRoot } from "react-dom/client";
import { MantineProvider, createTheme } from "@mantine/core";
import "@mantine/core/styles.css";
import "@fontsource-variable/noto-sans-sc";
import "@fontsource-variable/noto-serif-sc";
import "@fontsource/ibm-plex-mono/latin-500.css";
import { App } from "./App";

const theme = createTheme({
  fontFamily: "var(--sans)",
  fontFamilyMonospace: "var(--mono)",
  headings: { fontFamily: "var(--sans)" },
  defaultRadius: "md",
  primaryColor: "teal",
});

createRoot(document.getElementById("root")!).render(
  <MantineProvider theme={theme} forceColorScheme="light">
    <App />
  </MantineProvider>,
);
