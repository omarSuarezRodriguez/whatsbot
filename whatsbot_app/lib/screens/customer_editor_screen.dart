import 'package:flutter/material.dart';

import '../models/customer.dart';
import '../services/api_client.dart';
import '../theme/whatsapp_theme.dart';

class CustomerEditorScreen extends StatefulWidget {
  const CustomerEditorScreen({super.key, this.customer});

  final Customer? customer;

  @override
  State<CustomerEditorScreen> createState() => _CustomerEditorScreenState();
}

class _CustomerEditorScreenState extends State<CustomerEditorScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _waIdCtrl;
  late final TextEditingController _nameCtrl;
  late final TextEditingController _phoneCtrl;
  late final TextEditingController _notesCtrl;
  late bool _blocked;
  bool _saving = false;

  bool get _isEdit => widget.customer != null;

  @override
  void initState() {
    super.initState();
    final c = widget.customer;
    _waIdCtrl = TextEditingController(text: c?.waId ?? '');
    _nameCtrl = TextEditingController(text: c?.name ?? '');
    _phoneCtrl = TextEditingController(text: c?.phone ?? '');
    _notesCtrl = TextEditingController(text: c?.notes ?? '');
    _blocked = c?.blocked ?? false;
  }

  @override
  void dispose() {
    _waIdCtrl.dispose();
    _nameCtrl.dispose();
    _phoneCtrl.dispose();
    _notesCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);
    try {
      if (_isEdit) {
        await apiClient.updateCustomer(
          widget.customer!.id,
          name: _nameCtrl.text.trim(),
          phone: _phoneCtrl.text.trim().isEmpty ? null : _phoneCtrl.text.trim(),
          notes: _notesCtrl.text.trim().isEmpty ? null : _notesCtrl.text.trim(),
          blocked: _blocked,
        );
      } else {
        await apiClient.createCustomer(
          waId: _waIdCtrl.text.trim(),
          name: _nameCtrl.text.trim().isEmpty ? null : _nameCtrl.text.trim(),
          phone: _phoneCtrl.text.trim().isEmpty ? null : _phoneCtrl.text.trim(),
          notes: _notesCtrl.text.trim().isEmpty ? null : _notesCtrl.text.trim(),
        );
      }
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() => _saving = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: WhatsAppTheme.headerGreen,
        foregroundColor: Colors.white,
        title: Text(_isEdit ? 'Editar cliente' : 'Nuevo cliente'),
        actions: [
          if (_saving)
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16),
              child: Center(child: SizedBox(width: 20, height: 20, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))),
            )
          else
            TextButton(
              onPressed: _save,
              child: const Text('Guardar', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            ),
        ],
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (!_isEdit) ...[
              _Field(
                controller: _waIdCtrl,
                label: 'WhatsApp ID *',
                hint: 'Ej: 573001234567',
                icon: Icons.phone,
                validator: (v) {
                  if (v == null || v.trim().length < 5) return 'Ingresa un número de WhatsApp válido';
                  return null;
                },
              ),
              const SizedBox(height: 16),
            ],
            _Field(
              controller: _nameCtrl,
              label: 'Nombre',
              icon: Icons.person,
            ),
            const SizedBox(height: 16),
            _Field(
              controller: _phoneCtrl,
              label: 'Teléfono',
              icon: Icons.call,
              keyboardType: TextInputType.phone,
            ),
            const SizedBox(height: 16),
            _Field(
              controller: _notesCtrl,
              label: 'Notas',
              icon: Icons.note,
              maxLines: 3,
            ),
            if (_isEdit) ...[
              const SizedBox(height: 16),
              SwitchListTile(
                value: _blocked,
                onChanged: (v) => setState(() => _blocked = v),
                title: const Text('Bloqueado'),
                subtitle: const Text('El bot no responde a este usuario'),
                activeColor: Colors.red,
                tileColor: _blocked ? Colors.red.shade50 : null,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _Field extends StatelessWidget {
  const _Field({
    required this.controller,
    required this.label,
    this.hint,
    this.icon,
    this.validator,
    this.keyboardType,
    this.maxLines = 1,
  });

  final TextEditingController controller;
  final String label;
  final String? hint;
  final IconData? icon;
  final String? Function(String?)? validator;
  final TextInputType? keyboardType;
  final int maxLines;

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: controller,
      validator: validator,
      keyboardType: keyboardType,
      maxLines: maxLines,
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        prefixIcon: icon != null ? Icon(icon) : null,
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
        filled: true,
        fillColor: Colors.grey.shade50,
      ),
    );
  }
}
