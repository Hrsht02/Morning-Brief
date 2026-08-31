import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Navbar from "./components/Navbar";
import Loader from "./components/Loader";
import Login from "./pages/Login"; import Signup from "./pages/Signup"; import Onboarding from "./pages/Onboarding";
import DailyEdition from "./pages/DailyEdition"; import Preferences from "./pages/Preferences"; import Admin from "./pages/Admin";
import ApprovedNews from "./pages/ApprovedNews"; import CountrySources from "./pages/CountrySources";
function ProtectedRoute({children,requireAdmin=false,requireOnboarded=false}){const{user,loading}=useAuth();if(loading)return <Loader text="Loading..."/>;if(!user)return <Navigate to="/login" replace/>;if(requireAdmin&&!user.is_admin)return <Navigate to="/edition" replace/>;if(requireOnboarded&&!user.onboarded)return <Navigate to="/onboarding" replace/>;return children;}
function HomeRedirect(){const{user,loading}=useAuth();if(loading)return <Loader text="Loading..."/>;if(!user)return <Navigate to="/login" replace/>;if(!user.onboarded)return <Navigate to="/onboarding" replace/>;return <Navigate to="/edition" replace/>;}
function AppRoutes(){return <BrowserRouter><Navbar/><Routes><Route path="/" element={<HomeRedirect/>}/><Route path="/login" element={<Login/>}/><Route path="/signup" element={<Signup/>}/><Route path="/onboarding" element={<ProtectedRoute><Onboarding/></ProtectedRoute>}/><Route path="/edition" element={<ProtectedRoute requireOnboarded><DailyEdition/></ProtectedRoute>}/><Route path="/preferences" element={<ProtectedRoute requireOnboarded><Preferences/></ProtectedRoute>}/><Route path="/admin" element={<ProtectedRoute requireAdmin><Admin/></ProtectedRoute>}/><Route path="/admin/approved" element={<ProtectedRoute requireAdmin><ApprovedNews/></ProtectedRoute>}/><Route path="/admin/country-sources" element={<ProtectedRoute requireAdmin><CountrySources/></ProtectedRoute>}/><Route path="*" element={<Navigate to="/" replace/>}/></Routes></BrowserRouter>;}
export default function App(){return <AuthProvider><AppRoutes/></AuthProvider>;}
