/* Старый адрес контура ведёт на страницу участка.

   Отдельной страницы у загруженного контура больше нет: он открывается
   тем же экраном, что и участок набора, со всеми вкладками. Адрес
   /app/contours/:id остался в ссылках из переписки и в мастере, и ломать
   его незачем — он просто переадресуется. */

import { Navigate, useParams } from "react-router-dom";

export default function ContourRedirect() {
  const { id } = useParams();
  return <Navigate to={id ? `/app/area/${id}` : "/app/areas"} replace />;
}
