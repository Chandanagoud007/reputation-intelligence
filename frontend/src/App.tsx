import React, { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import { isAuthenticated } from "./api/auth";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 5000,
    },
  },
});

function App() {
  const [authed, setAuthed] = useState(isAuthenticated());

  return (
    <QueryClientProvider client={queryClient}>
      {authed ? <Dashboard /> : <Login onSuccess={() => setAuthed(true)} />}
    </QueryClientProvider>
  );
}

export default App;
