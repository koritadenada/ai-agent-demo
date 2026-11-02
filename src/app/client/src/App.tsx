import { createBrowserRouter, RouterProvider } from 'react-router';
import { ConfigProvider } from './lib/config';
import { Shell } from './components/ui';
import { Overview, ReviewDetail, ReviewList } from './pages/review';
import { QuoteDetail, Quotes } from './pages/negotiator';
import { PortCall, PortCalls } from './pages/portcalls';
import { Assistant } from './pages/assistant';

const router = createBrowserRouter([
  {
    element: <Shell />,
    children: [
      { path: '/', element: <Overview /> },
      { path: '/review', element: <ReviewList /> },
      { path: '/review/:id', element: <ReviewDetail /> },
      { path: '/negotiator', element: <Quotes /> },
      { path: '/negotiator/:id', element: <QuoteDetail /> },
      { path: '/port-calls', element: <PortCalls /> },
      { path: '/port-calls/:id', element: <PortCall /> },
      { path: '/assistant', element: <Assistant /> },
    ],
  },
]);

export default function App() {
  return <ConfigProvider><RouterProvider router={router} /></ConfigProvider>;
}
