import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { LayoutDashboard, PlusCircle, History, Shield, AlertTriangle, ChevronLeft, ChevronRight } from 'lucide-react';
import { Separator } from '@/components/ui/separator';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

const mainNav = [
  { path: '/dashboard',    icon: LayoutDashboard, label: 'Dashboard' },
  { path: '/new-analysis', icon: PlusCircle,       label: 'New Analysis' },
  { path: '/history',      icon: History,          label: 'History' },
];

const adminNav = [
  { path: '/admin',        icon: Shield,        label: 'Admin' },
  { path: '/admin/errori', icon: AlertTriangle,  label: 'Error Log' },
];

function NavItem({ item, isActive, collapsed }) {
  const Icon = item.icon;

  const inner = (
    <Link
      to={item.path}
      className={`
        relative flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-all duration-150
        ${isActive
          ? 'bg-primary/8 text-primary'
          : 'text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
        }
      `}
    >
      <Icon className="w-5 h-5 shrink-0" />
      <AnimatePresence>
        {!collapsed && (
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="whitespace-nowrap"
          >
            {item.label}
          </motion.span>
        )}
      </AnimatePresence>
    </Link>
  );

  if (collapsed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{inner}</TooltipTrigger>
        <TooltipContent side="right" className="font-inter">{item.label}</TooltipContent>
      </Tooltip>
    );
  }

  return inner;
}

export default function Sidebar({ collapsed, setCollapsed, userRole }) {
  const location = useLocation();
  const isAdmin = userRole === 'admin';
  const prefersReduced = useReducedMotion();

  const isActive = (path) => location.pathname === path;

  return (
    <TooltipProvider delayDuration={0}>
      <motion.aside
        initial={false}
        animate={{ width: collapsed ? 64 : 240 }}
        transition={{ duration: prefersReduced ? 0 : 0.2, ease: [0.25, 0.46, 0.45, 0.94] }}
        className="relative h-full bg-sidebar border-r border-sidebar-border flex flex-col overflow-hidden"
      >
        {/* Logo */}
        <div className="h-16 flex items-center px-4 gap-3 shrink-0">
          <div className="w-8 h-8 rounded-lg brand-gradient flex items-center justify-center shrink-0">
            <span className="text-white font-bold text-sm">C</span>
          </div>
          <AnimatePresence>
            {!collapsed && (
              <motion.span
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -8 }}
                transition={{ duration: 0.15, ease: [0.25, 0.46, 0.45, 0.94] }}
                className="font-mono font-bold text-primary whitespace-nowrap"
              >
                ComplianceOS
              </motion.span>
            )}
          </AnimatePresence>
        </div>

        <Separator className="bg-sidebar-border" />

        {/* Main nav */}
        <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
          {mainNav.map((item) => (
            <NavItem key={item.path} item={item} isActive={isActive(item.path)} collapsed={collapsed} />
          ))}

          {isAdmin && (
            <>
              <div className="py-2">
                <Separator className="bg-sidebar-border" />
              </div>
              {adminNav.map((item) => (
                <NavItem key={item.path} item={item} isActive={isActive(item.path)} collapsed={collapsed} />
              ))}
            </>
          )}
        </nav>

        {/* Collapse toggle */}
        <div className="p-2 border-t border-sidebar-border">
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="w-full flex items-center justify-center h-8 rounded-md text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground transition-all duration-150 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
          >
            {collapsed
              ? <ChevronRight className="w-4 h-4" />
              : <ChevronLeft className="w-4 h-4" />
            }
          </button>
        </div>
      </motion.aside>
    </TooltipProvider>
  );
}
