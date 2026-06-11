class MenuItemModel {
  MenuItemModel({
    this.id,
    this.businessId,
    required this.externalId,
    required this.nombre,
    required this.precio,
    required this.categoria,
    required this.disponible,
  });

  int? id;
  String? businessId;
  String externalId;
  String nombre;
  double precio;
  String categoria;
  bool disponible;

  factory MenuItemModel.fromJson(Map<String, dynamic> json) {
    return MenuItemModel(
      id: json['id'] as int?,
      businessId: json['business_id'] as String?,
      externalId: (json['external_id'] ?? json['id'] ?? '').toString(),
      nombre: json['nombre'] as String? ?? '',
      precio: (json['precio'] as num?)?.toDouble() ?? 0,
      categoria: json['categoria'] as String? ?? '',
      disponible: json['disponible'] as bool? ?? true,
    );
  }

  Map<String, dynamic> toApiJson() {
    return {
      'id': externalId.isNotEmpty ? externalId : nombre.hashCode.toString(),
      'external_id': externalId,
      'nombre': nombre,
      'precio': precio,
      'categoria': categoria,
      'disponible': disponible,
    };
  }

  MenuItemModel copyWith({
    String? externalId,
    String? nombre,
    double? precio,
    String? categoria,
    bool? disponible,
  }) {
    return MenuItemModel(
      id: id,
      businessId: businessId,
      externalId: externalId ?? this.externalId,
      nombre: nombre ?? this.nombre,
      precio: precio ?? this.precio,
      categoria: categoria ?? this.categoria,
      disponible: disponible ?? this.disponible,
    );
  }
}
