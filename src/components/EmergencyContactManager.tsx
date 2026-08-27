import React, { useState } from "react";
import { EmergencyContact } from "../types";
import { Users, UserPlus, Phone, ShieldCheck, Trash2, Star } from "lucide-react";

interface EmergencyContactManagerProps {
  contacts: EmergencyContact[];
  onUpdateContacts: (contacts: EmergencyContact[]) => void;
}

export const EmergencyContactManager: React.FC<EmergencyContactManagerProps> = ({
  contacts,
  onUpdateContacts,
}) => {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [relationship, setRelationship] = useState("Family");

  const handleAddContact = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !phone.trim()) return;

    const newContact: EmergencyContact = {
      id: "contact-" + Date.now(),
      name: name.trim(),
      phone: phone.trim(),
      relationship,
      primary: contacts.length === 0,
    };

    onUpdateContacts([...contacts, newContact]);
    setName("");
    setPhone("");
  };

  const handleRemoveContact = (id: string) => {
    onUpdateContacts(contacts.filter((c) => c.id !== id));
  };

  const handleSetPrimary = (id: string) => {
    onUpdateContacts(
      contacts.map((c) => ({
        ...c,
        primary: c.id === id,
      }))
    );
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl flex flex-col gap-4">
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-lg bg-red-500/20 text-red-400 border border-red-500/30">
            <Users className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-100">Emergency Contacts (SOS SMS)</h3>
            <p className="text-xs text-slate-400">Broadcasting GPS & Fall Alerts on Unacknowledged Impact</p>
          </div>
        </div>
      </div>

      {/* Add Contact Form */}
      <form onSubmit={handleAddContact} className="grid grid-cols-1 sm:grid-cols-3 gap-2 bg-slate-950 p-3 rounded-xl border border-slate-800 text-xs">
        <input
          type="text"
          placeholder="Contact Name (e.g. Sarah Shahane)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-slate-100 focus:outline-none focus:border-red-500"
        />
        <input
          type="text"
          placeholder="Phone (+1 555-0192)"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-slate-100 focus:outline-none focus:border-red-500"
        />
        <div className="flex gap-2">
          <select
            value={relationship}
            onChange={(e) => setRelationship(e.target.value)}
            className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-slate-100 focus:outline-none focus:border-red-500 flex-1"
          >
            <option value="Family">Family</option>
            <option value="Caregiver">Caregiver</option>
            <option value="Doctor">Doctor</option>
            <option value="Neighbor">Neighbor</option>
          </select>
          <button
            type="submit"
            className="px-3 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg font-medium transition flex items-center gap-1 shrink-0"
          >
            <UserPlus className="w-3.5 h-3.5" /> Add
          </button>
        </div>
      </form>

      {/* Contacts List */}
      <div className="flex flex-col gap-2">
        {contacts.map((contact) => (
          <div
            key={contact.id}
            className="bg-slate-950 p-3 rounded-xl border border-slate-800 flex items-center justify-between gap-3 text-xs"
          >
            <div className="flex items-center gap-3">
              <button
                onClick={() => handleSetPrimary(contact.id)}
                title={contact.primary ? "Primary Contact" : "Set as Primary"}
                className={`p-1.5 rounded-lg border transition ${
                  contact.primary
                    ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                    : "bg-slate-900 text-slate-500 border-slate-800 hover:text-slate-300"
                }`}
              >
                <Star className="w-4 h-4 fill-current" />
              </button>
              <div>
                <p className="font-semibold text-slate-100 flex items-center gap-2">
                  {contact.name}
                  {contact.primary && (
                    <span className="text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/30 px-1.5 py-0.2 rounded font-mono">
                      PRIMARY
                    </span>
                  )}
                </p>
                <p className="text-slate-400 font-mono text-[11px] flex items-center gap-2">
                  <span>{contact.relationship}</span>
                  <span>•</span>
                  <span>{contact.phone}</span>
                </p>
              </div>
            </div>

            <button
              onClick={() => handleRemoveContact(contact.id)}
              className="p-1.5 text-slate-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};
