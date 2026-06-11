class Customer {
  Customer({
    required this.id,
    required this.businessId,
    required this.waId,
    this.name,
    this.phone,
    this.notes,
    required this.blocked,
    required this.createdAt,
    required this.updatedAt,
  });

  final int id;
  final String businessId;
  final String waId;
  final String? name;
  final String? phone;
  final String? notes;
  final bool blocked;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory Customer.fromJson(Map<String, dynamic> json) {
    return Customer(
      id: json['id'] as int,
      businessId: json['business_id'] as String,
      waId: json['wa_id'] as String,
      name: json['name'] as String?,
      phone: json['phone'] as String?,
      notes: json['notes'] as String?,
      blocked: json['blocked'] as bool? ?? false,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }

  String get displayName => name?.isNotEmpty == true ? name! : waId;

  Customer copyWith({
    String? name,
    String? phone,
    String? notes,
    bool? blocked,
  }) {
    return Customer(
      id: id,
      businessId: businessId,
      waId: waId,
      name: name ?? this.name,
      phone: phone ?? this.phone,
      notes: notes ?? this.notes,
      blocked: blocked ?? this.blocked,
      createdAt: createdAt,
      updatedAt: updatedAt,
    );
  }
}
