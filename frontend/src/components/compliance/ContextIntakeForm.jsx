// @ts-nocheck
import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { ArrowRight } from 'lucide-react';

const STANDARDS = [
  { id: 'ISO 9001:2015',  label: 'ISO 9001:2015',  sub: 'Quality Management' },
  { id: 'ISO 14001:2015', label: 'ISO 14001:2015', sub: 'Environmental Management' },
  { id: 'ISO 45001:2018', label: 'ISO 45001:2018', sub: 'Occupational Health & Safety' },
];

const SECTORS = [
  'Construction', 'Manufacturing', 'Services',
  'Logistics', 'Healthcare', 'Energy', 'Other',
];

const EMPLOYEE_RANGES = ['1–10', '11–50', '51–250', '250+'];
const SITE_OPTIONS    = ['1', '2–5', '5+'];
const CERT_OPTIONS    = [
  { value: 'yes',         label: 'Yes' },
  { value: 'no',          label: 'No' },
  { value: 'in_progress', label: 'In progress' },
];

function FieldGroup({ labelId, label, required, children }) {
  return (
    <div className="space-y-1.5">
      <span
        id={labelId}
        className="text-sm font-medium text-foreground"
        aria-hidden={!labelId}
      >
        {label}{required && <span className="text-destructive ml-0.5" aria-hidden="true">*</span>}
        {required && <span className="sr-only">(required)</span>}
      </span>
      {children}
    </div>
  );
}

export default function ContextIntakeForm({ onContinue }) {
  const [form, setForm] = useState({
    company_name:   '',
    sector:         '',
    employee_range: '',
    norms:          [],
    certified:      '',
    sites_count:    '',
  });

  const set = (key, value) => setForm((f) => ({ ...f, [key]: value }));

  const toggleNorm = (id) => {
    setForm((f) => ({
      ...f,
      norms: f.norms.includes(id)
        ? f.norms.filter((n) => n !== id)
        : [...f.norms, id],
    }));
  };

  const isValid =
    form.company_name.trim().length > 0 &&
    form.sector &&
    form.employee_range &&
    form.norms.length > 0 &&
    form.certified &&
    form.sites_count;

  const handleContinue = () => {
    if (!isValid) return;
    onContinue({
      company_name:   form.company_name.trim(),
      sector:         form.sector,
      employee_range: form.employee_range,
      norms:          form.norms,
      certified:      form.certified,
      sites_count:    form.sites_count,
    });
  };

  return (
    <div className="space-y-6">
      <div className="space-y-1.5">
        <Label htmlFor="company_name" className="text-sm font-medium text-foreground">
          Company name<span className="text-destructive ml-0.5" aria-hidden="true">*</span>
          <span className="sr-only">(required)</span>
        </Label>
        <Input
          id="company_name"
          placeholder="e.g. Hartley Construction Ltd"
          value={form.company_name}
          onChange={(e) => set('company_name', e.target.value)}
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        <FieldGroup labelId="label-sector" label="Industry sector" required>
          <Select value={form.sector} onValueChange={(v) => set('sector', v)}>
            <SelectTrigger aria-labelledby="label-sector">
              <SelectValue placeholder="Select sector" />
            </SelectTrigger>
            <SelectContent>
              {SECTORS.map((s) => (
                <SelectItem key={s} value={s}>{s}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FieldGroup>

        <FieldGroup labelId="label-employees" label="Number of employees" required>
          <Select value={form.employee_range} onValueChange={(v) => set('employee_range', v)}>
            <SelectTrigger aria-labelledby="label-employees">
              <SelectValue placeholder="Select range" />
            </SelectTrigger>
            <SelectContent>
              {EMPLOYEE_RANGES.map((r) => (
                <SelectItem key={r} value={r}>{r}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FieldGroup>
      </div>

      <fieldset className="space-y-1.5">
        <legend className="text-sm font-medium text-foreground">
          Standards to assess<span className="text-destructive ml-0.5" aria-hidden="true">*</span>
          <span className="sr-only">(required)</span>
        </legend>
        <div className="space-y-2.5 pt-1">
          {STANDARDS.map((s) => (
            <label
              key={s.id}
              className="flex items-center gap-3 cursor-pointer group"
            >
              <Checkbox
                id={`norm-${s.id}`}
                checked={form.norms.includes(s.id)}
                onCheckedChange={() => toggleNorm(s.id)}
              />
              <span className="flex flex-col">
                <span className="text-sm font-medium font-mono text-foreground">{s.label}</span>
                <span className="text-xs text-muted-foreground">{s.sub}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        <FieldGroup labelId="label-certified" label="Currently certified?" required>
          <Select value={form.certified} onValueChange={(v) => set('certified', v)}>
            <SelectTrigger aria-labelledby="label-certified">
              <SelectValue placeholder="Select" />
            </SelectTrigger>
            <SelectContent>
              {CERT_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FieldGroup>

        <FieldGroup labelId="label-sites" label="Number of operating sites" required>
          <Select value={form.sites_count} onValueChange={(v) => set('sites_count', v)}>
            <SelectTrigger aria-labelledby="label-sites">
              <SelectValue placeholder="Select" />
            </SelectTrigger>
            <SelectContent>
              {SITE_OPTIONS.map((o) => (
                <SelectItem key={o} value={o}>{o}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FieldGroup>
      </div>

      <div className="pt-2">
        <Button onClick={handleContinue} disabled={!isValid} className="gap-2">
          Continue
          <ArrowRight className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
}
